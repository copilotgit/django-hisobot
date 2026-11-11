from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import conf, report


def _maybe_login_required(view):
    """Login is asked for only when HISOBOT_LOGIN_REQUIRED is on."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if conf.login_required() and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return view(request, *args, **kwargs)
    return wrapper


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=conf.utc_offset_hours()))).date().isoformat()


@require_GET
@_maybe_login_required
def report_view(request):
    data = report.load()
    state = report.status()
    if report.is_stale(data) and not state["running"]:
        state["running"] = report.start_refresh()
    can_refresh = request.user.is_staff
    return render(request, "hisobot/report.html", {
        "data": data,
        "today": _today(),
        "state": state,
        "can_refresh": can_refresh,
        "configured": bool(conf.api_url() and conf.api_token()),
    })


@require_POST
def refresh_view(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Faqat xodimlar (is_staff) ma'lumotlarni yangilay oladi.")
    report.start_refresh()
    return redirect("hisobot:report")


@require_GET
def data_view(request):
    """The saved report as JSON - for programs such as the Nazorat jadvali
    desktop app (rooms busy with lessons and exams). Same access as the page;
    with HISOBOT_LOGIN_REQUIRED on, the HISOBOT_API_KEY opens it too."""
    if conf.login_required() and not request.user.is_authenticated:
        key = conf.api_key()
        given = request.headers.get("X-Hisobot-Key") or request.GET.get("key", "")
        if not key or not secrets.compare_digest(given.encode(), key.encode()):
            return JsonResponse({"detail": "Kirish talab qilinadi (X-Hisobot-Key)."}, status=403)
    path = conf.data_file()
    if not path.exists():
        return JsonResponse({"detail": "Hisobot hali yuklanmagan (python manage.py hisobot_refresh)."}, status=404)
    response = HttpResponse(path.read_bytes(), content_type="application/json; charset=utf-8")
    if not conf.login_required():
        response["Access-Control-Allow-Origin"] = "*"
    return response


@require_GET
@_maybe_login_required
def status_view(request):
    state = report.status()
    data = report.load()
    state["generated"] = data.get("generated") if data else None
    return JsonResponse(state)
