from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

# src/config/urls.py

@login_required
def dashboard_root(request):
    return render(request, "dashboard/index.html")

# 起動確認のため
def healthz(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("", dashboard_root, name="dashboard_root"),
    path("admin/", admin.site.urls),
    path("healthz/", healthz),

    # accounts: LOGIN_URL="/auth/login/" と整合させる
    path("auth/", include("apps.accounts.urls")),

    # teams
    path("teams/", include("apps.teams.urls")),

    # quests
    path("quests/", include("apps.quests.urls")),

    # notifications
    path("notifications/", include("apps.notifications.urls")),

    # accounts
    path("accounts/", include("apps.accounts.urls")),
]
