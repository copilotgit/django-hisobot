from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden, JsonResponse
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
@_maybe_login_required
def status_view(request):
    state = report.status()
    data = report.load()
    state["generated"] = data.get("generated") if data else None
    return JsonResponse(state)
