from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from apps.common.api.health import healthz

def root(request):
    return JsonResponse({"service": "django-starter", "status": "ok"})

urlpatterns = [
    path("",root),
    path("admin/", admin.site.urls),
    path("healthz/", healthz),
]
