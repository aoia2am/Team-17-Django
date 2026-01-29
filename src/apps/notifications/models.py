# src/apps/notifications/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    MEMBER_COMPLETED = "member_completed", "メンバー達成"
    DAILY_READY = "daily_ready", "今日のクエスト提示"
    TEAM_RANK_UP = "team_rank_up", "チームランクアップ"
    SYSTEM = "system", "システム"


class Notification(models.Model):
    """
    チーム内通知（フィード）。

    MVP方針:
    - チーム単位で保存して一覧表示（SNSのタイムラインのミニマム版）
    - 誰が読んだかは後回しでも成立するが、read管理も軽く入れておくと強い

    設計メモ:
    - message はAI文言などで200文字を超える可能性があるため TextField を採用
    - 一覧は team + created_at で引き、並び順はクエリ側で order_by("-created_at") を使う
    （Index.fields に "-created_at" のような降順指定は環境差で事故りやすい）
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    type = models.CharField(max_length=30, choices=NotificationType.choices)

    # AIコメント導入を見据えて TextField（UIはテンプレ側で必要に応じて省略表示）
    message = models.TextField()

    # どのユーザー起因か（達成通知など）
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acted_notifications",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications_notification"
        indexes = [
            # チームのタイムライン取得用（並び順はクエリ側で -created_at）
            models.Index(fields=["team", "created_at"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self) -> str:
        return f"Notification(team={self.team_id}, type={self.type})"


class NotificationRead(models.Model):
    """
    通知の既読管理（ユーザー単位）。

    NOTE:
    - Hackathonでは「未読バッジ」までやると発表映えする。
    - 既読の重複登録は UniqueConstraint で防ぐ。
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="reads",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_reads",
    )
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications_read"
        constraints = [
            models.UniqueConstraint(fields=["notification", "user"], name="uq_notification_read"),
        ]
        indexes = [
            # ユーザーの既読履歴を引く（並び順はクエリ側で -read_at）
            models.Index(fields=["user", "read_at"]),
        ]

    def __str__(self) -> str:
        return f"NotificationRead(notification={self.notification_id}, user={self.user_id})"
