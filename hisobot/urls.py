from django.urls import path

from . import views

app_name = "hisobot"

urlpatterns = [
    path("", views.report_view, name="report"),
    path("refresh/", views.refresh_view, name="refresh"),
    path("status/", views.status_view, name="status"),
    path("data.json", views.data_view, name="data"),
]
