from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include

# src/config/urls.py
def root(request):
    return JsonResponse({"service": "django-starter", "status": "ok"})

# 起動確認のため
def healthz(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("",root),
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
]
