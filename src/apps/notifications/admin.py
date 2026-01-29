# src/apps/notifications/admin.py
from django.contrib import admin

from .models import Notification, NotificationRead


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    運営・デバッグ用の通知一覧。
    """
    list_display = ("id", "team", "type", "actor", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("message",)
    raw_id_fields = ("team", "actor")
    ordering = ("-created_at",)


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
    """
    既読管理（未読バッジの裏付け）。

    NOTE:
    - read は爆増しやすいので raw_id_fields 推奨
    """
    list_display = ("id", "notification", "user", "read_at")
    list_filter = ("read_at",)
    raw_id_fields = ("notification", "user")
    ordering = ("-read_at",)
