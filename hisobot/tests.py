"""python manage.py test hisobot - no network: HEMIS answers are faked."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from . import conf, report
from .hemis import HemisClient, HemisError

TS = 1762732800  # 2025-11-10 00:00 UTC (a Monday)

AUDITORIUMS = [
    {"code": 101, "name": "101-xona", "auditoriumType": {"name": "Ma'ruza"}, "volume": 60,
     "building": {"id": 1, "name": "Bosh bino "}, "active": True},
    {"code": 102, "name": "102-xona", "auditoriumType": {"name": "Amaliy"}, "volume": 30,
     "building": {"id": 1, "name": "Bosh bino"}, "active": False},
]
FACULTIES = [{"id": 5, "name": "Fizika-matematika", "structureType": {"code": "11"}},
             {"id": 6, "name": "Kafedra", "structureType": {"code": "12"}}]
LESSONS = [
    {"id": 1, "auditorium": AUDITORIUMS[0], "lesson_date": TS, "subject": {"name": "Algebra"},
     "trainingType": {"name": "Ma'ruza"}, "employee": {"name": "Teacher A"}, "group": {"name": "G-1"},
     "lessonPair": {"name": "1", "start_time": "08:30", "end_time": "09:50"}},
    {"id": 2, "auditorium": AUDITORIUMS[0], "lesson_date": TS, "subject": {"name": "Algebra"},
     "trainingType": {"name": "Ma'ruza"}, "employee": {"name": "Teacher A"}, "group": {"name": "G-2"},
     "lessonPair": {"name": "1", "start_time": "08:30", "end_time": "09:50"}},
]
EXAMS = [{"id": 9, "auditorium": AUDITORIUMS[0], "examDate": TS, "subject": {"name": "Fizika"},
          "examType": {"name": "1-ON"}, "employee": {"name": "Teacher B"}, "group": {"name": "G-1"},
          "lessonPair": {"name": "2"}}]


class TempDataFile(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_file = Path(self.tmp.name) / "hisobot_data.json"
        settings_override = override_settings(
            HISOBOT_DATA_FILE=str(self.data_file), HEMIS_API_URL="https://hemis.example/rest/v1/data",
            HEMIS_API_TOKEN="test-token", HISOBOT_LOGIN_REQUIRED=False, HISOBOT_AUTO_REFRESH_HOURS=0)
        settings_override.enable()
        self.addCleanup(settings_override.disable)


class BuildReportTests(TestCase):
    def test_events_rooms_and_weeks(self):
        data = report.build_report(AUDITORIUMS, {1: "Bosh bino"}, LESSONS, EXAMS)
        self.assertEqual([r["n"] for r in data["rooms"]], ["101-xona"])  # inactive & unused room hidden
        self.assertEqual(data["weeks"], ["2025-11-10"])
        day = data["events"]["101"]["2025-11-10"]
        self.assertEqual(sorted(e[1] for e in day), [0, 0, 1])  # two lesson rows, one exam
        self.assertEqual(tuple(data["pairTimes"]["1"]), ("08:30", "09:50"))


class ConfTests(TestCase):
    @override_settings(HEMIS_API_URL="https://x/rest/v1/data")
    def test_settings_win_and_slash_added(self):
        self.assertEqual(conf.api_url(), "https://x/rest/v1/data/")

    def test_env_used_when_not_in_settings(self):
        with mock.patch.dict("os.environ", {"HISOBOT_LOGIN_REQUIRED": "true", "HISOBOT_WORKERS": "5"}):
            self.assertTrue(conf.login_required())
            self.assertEqual(conf.workers(), 5)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.headers = payload, status, {}

    def json(self):
        return self.payload


class HemisClientTests(TestCase):
    def test_needs_url_and_token(self):
        with self.assertRaises(HemisError):
            HemisClient("", "")

    def test_pages_are_joined_and_token_sent(self):
        seen = []

        def fake_get(url, params, headers, timeout):
            seen.append(headers["Authorization"])
            page = params["page"]
            return FakeResponse({"success": True, "data": {"items": [{"id": page}],
                                                           "pagination": {"pageCount": 3}}})
        with mock.patch("hisobot.hemis.requests.get", fake_get):
            items = HemisClient("https://x/", "abc", log=lambda t: None).fetch_all("auditorium-list")
        self.assertEqual(sorted(i["id"] for i in items), [1, 2, 3])
        self.assertEqual(set(seen), {"Bearer abc"})

    def test_rejected_token(self):
        with mock.patch("hisobot.hemis.requests.get", lambda *a, **k: FakeResponse({}, 401)):
            with self.assertRaises(HemisError):
                HemisClient("https://x/", "bad", log=lambda t: None).get("auditorium-list", {})


def fake_client(*args, **kwargs):
    client = mock.Mock()
    client.auditoriums.return_value = (AUDITORIUMS, {1: "Bosh bino"})
    client.faculties.return_value = FACULTIES[:1]
    client.lessons.return_value = LESSONS
    client.exams.return_value = EXAMS
    return client


class RefreshAndViewTests(TempDataFile):
    def test_command_saves_report(self):
        with mock.patch("hisobot.report.HemisClient", fake_client):
            call_command("hisobot_refresh", stdout=open(self.tmp.name + "/out.txt", "w"))
        data = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertIn("101", data["events"])
        self.assertFalse(report.status()["running"])  # lock released

    def test_page_empty_then_with_data(self):
        response = self.client.get(reverse("hisobot:report"))
        self.assertContains(response, "Hisobot hali yuklanmagan")
        with mock.patch("hisobot.report.HemisClient", fake_client):
            report.refresh(log=lambda t: None)
        response = self.client.get(reverse("hisobot:report"))
        self.assertContains(response, 'id="hisobot-data"')
        self.assertContains(response, "101-xona")
        self.assertNotContains(response, "test-token")  # the token never reaches the page

    def test_refresh_button_is_staff_only(self):
        self.assertEqual(self.client.post(reverse("hisobot:refresh")).status_code, 403)
        User.objects.create_user("admin", password="x", is_staff=True)
        self.client.login(username="admin", password="x")
        with mock.patch("hisobot.report.start_refresh") as start:
            response = self.client.post(reverse("hisobot:refresh"))
        self.assertEqual(response.status_code, 302)
        start.assert_called_once()

    @override_settings(HISOBOT_LOGIN_REQUIRED=True)
    def test_login_required_option(self):
        response = self.client.get(reverse("hisobot:report"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    @override_settings(HEMIS_API_TOKEN="")
    def test_not_configured_message(self):
        self.assertContains(self.client.get(reverse("hisobot:report")), "HEMIS_API_TOKEN")

    def test_data_json(self):
        self.assertEqual(self.client.get(reverse("hisobot:data")).status_code, 404)
        with mock.patch("hisobot.report.HemisClient", fake_client):
            report.refresh(log=lambda t: None)
        data = self.client.get(reverse("hisobot:data")).json()
        self.assertIn("101", data["events"])
        self.assertNotIn("test-token", json.dumps(data))

    @override_settings(HISOBOT_LOGIN_REQUIRED=True, HISOBOT_API_KEY="k123")
    def test_data_json_key_when_login_required(self):
        with mock.patch("hisobot.report.HemisClient", fake_client):
            report.refresh(log=lambda t: None)
        self.assertEqual(self.client.get(reverse("hisobot:data")).status_code, 403)
        self.assertEqual(self.client.get(reverse("hisobot:data"), HTTP_X_HISOBOT_KEY="bad").status_code, 403)
        self.assertEqual(self.client.get(reverse("hisobot:data"), HTTP_X_HISOBOT_KEY="k123").status_code, 200)

    def test_status_endpoint(self):
        data = self.client.get(reverse("hisobot:status")).json()
        self.assertEqual(data["running"], False)
