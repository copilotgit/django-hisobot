"""
HEMIS REST API client (``/rest/v1/data/``), with a Bearer token.

    auditorium-list   -> rooms (the building list is taken from the rooms)
    department-list   -> faculties (structureType code 11)
    schedule-list     -> lessons, fetched for every faculty
    subject-exam-list -> exams (room, date, pair), fetched for every
                         semester / exam type (exam-list only has online
                         tests without rooms)
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import requests

LIMIT = 200
RETRIES = 8
FACULTY_TYPE = "11"
SEMESTERS = [str(code) for code in range(11, 23)]  # 1-semestr .. 12-semestr
EXAM_TYPES = [str(code) for code in range(11, 21)]  # 13 Yakuniy, 14 Umumiy, 17 1-on, 18 2-on, ...


class HemisError(Exception):
    pass


class HemisClient:
    def __init__(self, api_url: str, token: str, workers: int = 3, log=print):
        if not api_url or not token:
            raise HemisError("HEMIS_API_URL va HEMIS_API_TOKEN sozlanmagan (.env faylini to'ldiring).")
        self.api_url = api_url if api_url.endswith("/") else api_url + "/"
        self.token = token
        self.workers = workers
        self.log = log

    def get(self, endpoint: str, params: dict, retries: int = RETRIES, timeout: int = 120) -> dict:
        headers = {"accept": "application/json", "Authorization": f"Bearer {self.token}"}
        error = None
        for attempt in range(retries):
            try:
                response = requests.get(self.api_url + endpoint, params=params, headers=headers, timeout=timeout)
                if response.status_code in (401, 403):
                    raise HemisError(f"HEMIS tokeni qabul qilinmadi ({response.status_code}). HEMIS_API_TOKEN ni tekshiring.")
                data = response.json()
                if data.get("success"):
                    return data["data"]
                error = data.get("error")
                if "rate limit" not in str(error).lower():
                    break
                wait = int(response.headers.get("Retry-After") or 0) or 5 * (attempt + 1)
            except (requests.RequestException, ValueError) as exc:
                error = exc
                wait = 3 * (attempt + 1)
            if attempt + 1 < retries:
                time.sleep(wait)
        raise HemisError(f"{endpoint} {params}: {error}")

    def fetch_all(self, endpoint: str, **filters) -> list:
        """Every page of an endpoint (the page size is constant 200)."""
        first = self.get(endpoint, {"page": 1, "limit": LIMIT, **filters})
        items = list(first["items"])
        page_count = first["pagination"]["pageCount"]
        if page_count > 1:
            with ThreadPoolExecutor(self.workers) as pool:
                pages = pool.map(lambda p: self.get(endpoint, {"page": p, "limit": LIMIT, **filters}),
                                 range(2, page_count + 1))
                for page in pages:
                    items.extend(page["items"])
        return items

    # ---- the data the report needs
    def auditoriums(self) -> tuple[list, dict]:
        auditoriums = self.fetch_all("auditorium-list")
        buildings = {a["building"]["id"]: a["building"]["name"].strip() for a in auditoriums if a.get("building")}
        self.log(f"Auditoriyalar: {len(auditoriums)}, binolar: {len(buildings)}")
        return auditoriums, buildings

    def faculties(self) -> list:
        departments = self.fetch_all("department-list", active=1)
        faculties = [d for d in departments if d["structureType"]["code"] == FACULTY_TYPE]
        self.log(f"Fakultetlar: {len(faculties)}")
        return faculties

    def lessons(self, faculties: list) -> list:
        lessons = []
        for faculty in faculties:
            items = self.fetch_all("schedule-list", _faculty=faculty["id"])
            self.log(f"  {faculty['name']}: {len(items)} ta dars")
            lessons.extend(items)
        lessons = unique_by(lessons, lambda x: x["id"])
        self.log(f"Darslar: {len(lessons)}")
        return lessons

    def exams(self) -> list:
        exams = []
        for semester in SEMESTERS:
            # skip semesters without exams before trying every exam type
            if not self.get("subject-exam-list", {"page": 1, "limit": 1, "_semester": semester})["items"]:
                continue
            for exam_type in EXAM_TYPES:
                items = self.fetch_all("subject-exam-list", _semester=semester, _exam_type=exam_type)
                if items:
                    self.log(f"  {semester}-semestr kodi, nazorat turi {exam_type}: {len(items)} ta")
                exams.extend(items)
        exams = unique_by(exams, lambda x: x["id"])
        self.log(f"Imtihonlar: {len(exams)}")
        return exams


def unique_by(items: list, key) -> list:
    return list({key(item): item for item in items}.values())
