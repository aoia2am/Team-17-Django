from django.contrib import admin

from .models import Quest, DailyQuestSet, DailyQuestItem, QuestCompletion

# @admin.registerはadminのみが管理者画面に入れるという意味。

@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "difficulty", "category", "points", "is_active", "created_at")
    list_filter = ("difficulty", "category", "is_active")
    search_fields = ("name")
    ordering = ("difficulty", "category", "name")


@admin.register(DailyQuestSet)
class DailyQuestSetAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "date", "difficulty", "generated_by", "created_at")
    list_filter = ("difficulty", "generated_by", "date")
    raw_id_fields = ("team",)
    ordering = ("-date","team")


@admin.register(DailyQuestItem)
class DailyQuestItemAdmin(admin.ModelAdmin):
    list_display = ("id", "daily_set", "sort_order","quest")
    list_filter = ("daily_set__date", "daily_set__difficulty")
    raw_id_fields = ("daily_set", "quest")
    ordering = ("-daily_set__date","daily_set", "sort_order")


@admin.register(QuestCompletion)
class QuestCompletionAdmin(admin.ModelAdmin):
    list_display = ("id", "daily_item", "user", "completed_at")
    list_filter = ("completed_at", "daily_item__daily_set__date")
    raw_id_fields = ("daily_item", "user")
    ordering = ("-completed_at",)
