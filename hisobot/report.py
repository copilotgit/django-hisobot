"""
Builds the room occupancy report from the HEMIS data, and keeps it in a
JSON file (conf.data_file()) - the page only reads that file, because
downloading everything from HEMIS takes minutes.

refresh() downloads and saves; start_refresh() runs it on a background
thread, at most one at a time - also across several gunicorn workers (a lock
file next to the data file).
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import conf
from .hemis import HemisClient

LOCK_STALE_SECONDS = 3 * 60 * 60  # a lock older than this is from a crashed run


# ---------------------------------------------------------------- data processing

def utc_date(timestamp: int) -> date:
    return datetime.fromtimestamp(timestamp, timezone.utc).date()


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def pair_number(lesson_pair) -> int | None:
    try:
        return int(lesson_pair["name"])
    except (KeyError, TypeError, ValueError):
        return None


class Strings:
    """Stores repeated strings once; events keep only their index."""

    def __init__(self):
        self.items, self.index = [], {}

    def __call__(self, value) -> int:
        value = value or ""
        if value not in self.index:
            self.index[value] = len(self.items)
            self.items.append(value)
        return self.index[value]


def build_report(auditoriums: list, buildings: dict, lessons: list, exams: list, utc_offset: int = 5) -> dict:
    strings = Strings()
    rooms = {}
    for a in auditoriums:
        rooms[a["code"]] = {
            "c": a["code"], "n": a["name"], "t": (a.get("auditoriumType") or {}).get("name", ""),
            "v": a.get("volume") or 0, "b": (a.get("building") or {}).get("id"), "a": a.get("active", True),
        }

    events = {}  # room code -> date -> [[pair, kind (0 lesson, 1 exam), subject, type, employee, group], ...]
    pair_times = {}

    def add_event(auditorium, day, pair, row):
        if auditorium["code"] not in rooms:
            rooms[auditorium["code"]] = {"c": auditorium["code"], "n": auditorium.get("name", ""), "t": "",
                                         "v": auditorium.get("volume") or 0,
                                         "b": (auditorium.get("building") or {}).get("id"), "a": True}
        rooms[auditorium["code"]]["used"] = True
        events.setdefault(str(auditorium["code"]), {}).setdefault(day.isoformat(), []).append([pair] + row)

    for lesson in lessons:
        pair = pair_number(lesson.get("lessonPair"))
        if not lesson.get("auditorium") or not pair:
            continue
        lp = lesson["lessonPair"]
        pair_times.setdefault(pair, (lp.get("start_time", ""), lp.get("end_time", "")))
        add_event(lesson["auditorium"], utc_date(lesson["lesson_date"]), pair, [
            0,
            strings(lesson["subject"]["name"]),
            strings((lesson.get("trainingType") or {}).get("name")),
            strings((lesson.get("employee") or {}).get("name")),
            strings((lesson.get("group") or {}).get("name")),
        ])

    for exam in exams:
        pair = pair_number(exam.get("lessonPair"))
        if not exam.get("auditorium") or not pair or not exam.get("examDate"):
            continue
        add_event(exam["auditorium"], utc_date(exam["examDate"]), pair, [
            1,
            strings(exam["subject"]["name"]),
            strings((exam.get("examType") or {}).get("name")),
            strings((exam.get("employee") or {}).get("name")),
            strings((exam.get("group") or {}).get("name")),
        ])

    # active rooms (like HEMIS) and inactive rooms that still have lessons
    room_list = sorted((r for r in rooms.values() if r["a"] or r.get("used")), key=lambda r: r["n"])
    for room in room_list:
        room.pop("used", None)
        room.pop("a", None)
    used_buildings = {r["b"] for r in room_list}
    building_list = sorted(({"id": b, "name": name} for b, name in buildings.items() if b in used_buildings),
                           key=lambda b: b["name"])

    weeks = sorted({monday(date.fromisoformat(d)).isoformat() for days in events.values() for d in days})
    local = timezone(timedelta(hours=utc_offset))
    return {
        "generated": datetime.now(local).strftime("%d.%m.%Y %H:%M"),
        "generated_at": time.time(),
        "weeks": weeks,
        "buildings": building_list,
        "rooms": room_list,
        "pairs": max([8] + list(pair_times)),
        "pairTimes": {str(k): v for k, v in pair_times.items()},
        "strings": strings.items,
        "events": events,
    }


# ---------------------------------------------------------------- the saved report

def load() -> dict | None:
    try:
        return json.loads(conf.data_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(report: dict) -> None:
    path = conf.data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)  # readers never see a half-written file


def _status_file() -> Path:
    return conf.data_file().with_suffix(".status.json")


def _lock_file() -> Path:
    return conf.data_file().with_suffix(".lock")


def status() -> dict:
    """{"running": bool, "error": str, "finished": "dd.mm.yyyy hh:mm"}"""
    try:
        data = json.loads(_status_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    lock = _lock_file()
    data["running"] = lock.exists() and time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS
    return data


def _write_status(**values) -> None:
    try:
        _status_file().write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _acquire_lock() -> bool:
    lock = _lock_file()
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
        lock.unlink(missing_ok=True)
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def download(client: HemisClient, log=print) -> dict:
    """Everything the report needs, read with `client`, as the report."""
    auditoriums, buildings = client.auditoriums()
    faculties = client.faculties()
    log("Darslar yuklanmoqda...")
    lessons = client.lessons(faculties)
    exams = client.exams()
    return build_report(auditoriums, buildings, lessons, exams, conf.utc_offset_hours())


def refresh(log=print) -> dict:
    """Downloads everything from HEMIS and saves the report. Raises
    RuntimeError when another refresh is running."""
    if not _acquire_lock():
        raise RuntimeError("Ma'lumotlar allaqachon yangilanmoqda.")
    started = time.time()
    try:
        client = HemisClient(conf.api_url(), conf.api_token(), conf.workers(), log=log)
        report = download(client, log)
        _save(report)
        log(f"Hisobot saqlandi: {conf.data_file()} ({time.time() - started:.0f} s)")
        _write_status(error="", finished=report["generated"])
        return report
    except Exception as exc:
        _write_status(error=str(exc), finished="")
        raise
    finally:
        _lock_file().unlink(missing_ok=True)


def start_refresh() -> bool:
    """refresh() on a background thread; False if one is already running."""
    if status()["running"]:
        return False

    def run():
        try:
            refresh(log=lambda text: None)
        except Exception:
            traceback.print_exc()

    threading.Thread(target=run, daemon=True, name="hisobot-refresh").start()
    return True


def is_stale(report: dict | None) -> bool:
    hours = conf.auto_refresh_hours()
    if not hours:
        return False
    return report is None or time.time() - report.get("generated_at", 0) > hours * 3600
