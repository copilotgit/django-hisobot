# django-hisobot — Auditoriya bandligi

A reusable Django app that shows **which room is busy when** at a university that uses
**HEMIS**: every room × 6 days × 8 pairs, built from the HEMIS REST API.

- 🟩 **green** — lessons (the number = how many different lessons are in the room at that pair)
- 🟥 **red** — exams
- 🟨 **yellow** — lessons and exams at the same time

Filter by week and building; click a cell to see the subjects, teachers and groups.
It looks like HEMIS's own *Auditoriya bandligi* page (`/report/by-rooms`), but it also
shows **exams**, and anyone you allow can open it without a HEMIS account.

---

## Install (2 lines in your project)

1. Copy the `hisobot/` folder next to your `manage.py`
   (or `pip install git+https://github.com/copilotgit/django-hisobot.git`), then install the
   requirements:

   ```bash
   pip install -r requirements.txt   # Django, requests, python-dotenv
   ```

2. **settings.py** — add the app:

   ```python
   INSTALLED_APPS = [
       # ...
       "hisobot",
   ]
   ```

3. **urls.py** — add its URL:

   ```python
   from django.urls import include, path

   urlpatterns = [
       # ...
       path("hisobot/", include("hisobot.urls")),
   ]
   ```

4. **.env** — copy `.env.example` to `.env` next to `manage.py` and fill in your HEMIS:

   ```ini
   HEMIS_API_URL=https://student.<your-university>.uz/rest/v1/data/
   HEMIS_API_TOKEN=<your token>
   ```

   The API token comes from your HEMIS administrator. Keep it secret:
   `.env` is in `.gitignore`. Any of these values can also be set in `settings.py`
   instead (settings win over `.env`).

5. Load the data once and open `/hisobot/`:

   ```bash
   python manage.py hisobot_refresh
   ```

No database tables, no migrations.

## Keeping the data fresh

Downloading everything from HEMIS takes a few minutes, so the page shows the last
downloaded copy (a JSON file) and never waits for HEMIS. Refresh it in any of these ways:

| How | |
|---|---|
| `python manage.py hisobot_refresh` | by hand, or from **cron**: `0 6 * * * cd /srv/site && .venv/bin/python manage.py hisobot_refresh` |
| **HEMIS'dan yangilash** button on the page | shown to staff users (`is_staff`); runs in the background, the page reloads when done |
| `HISOBOT_AUTO_REFRESH_HOURS=12` | refreshes in the background when someone opens the page and the data is older than 12 hours |

Only one refresh runs at a time, even with several gunicorn workers.

## Settings

| Name | Default | |
|---|---|---|
| `HEMIS_API_URL` | — | your HEMIS REST API, e.g. `https://student.example.uz/rest/v1/data/` |
| `HEMIS_API_TOKEN` | — | HEMIS API token (secret) |
| `HISOBOT_LOGIN_REQUIRED` | `false` | `true` = only logged-in users see the report (uses your `LOGIN_URL`) |
| `HISOBOT_AUTO_REFRESH_HOURS` | `0` | see above; `0` = off |
| `HISOBOT_DATA_FILE` | `<BASE_DIR>/hisobot_data.json` | where the downloaded report is kept |
| `HISOBOT_WORKERS` | `3` | parallel requests to HEMIS (it rate-limits — keep it low) |
| `HISOBOT_UTC_OFFSET` | `5` | your time zone in hours from UTC (Tashkent = 5) |

The report contains teachers' and groups' names — consider `HISOBOT_LOGIN_REQUIRED=true`
if your site is public.

## URLs

| URL | |
|---|---|
| `/hisobot/` | the report |
| `/hisobot/refresh/` | POST, staff only — start a background refresh |
| `/hisobot/status/` | JSON: `{"running": false, "generated": "11.11.2026 08:00", "error": ""}` |

## What it reads from HEMIS

| Endpoint | For |
|---|---|
| `auditorium-list` | rooms and buildings |
| `department-list` | faculties (`structureType` 11) |
| `schedule-list` | lessons, per faculty |
| `subject-exam-list` | exams (room, date, pair), per semester and exam type |

## Tests

```bash
python manage.py test hisobot
```

They fake HEMIS's answers — no network and no token needed.

## License

MIT
