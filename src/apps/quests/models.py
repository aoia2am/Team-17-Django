# src/apps/quests/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class QuestDifficulty(models.TextChoices):
    # 表示も英語に統一（アプリコンセプト優先）
    EASY = "easy", "Easy"
    MEDIUM = "medium", "Medium"
    HARD = "hard", "Hard"


class QuestCategory(models.TextChoices):
    STRETCH = "stretch", "Stretch"
    MUSCLE = "muscle", "Muscle"


class DailyGeneratedBy(models.TextChoices):
    LOGIC = "logic", "Logic"
    AI = "ai", "AI"


class Quest(models.Model):
    """
    固定クエスト（DB seed 前提）。

    NOTE:
    - 「AI提案」は Quest を生成するのではなく、Quest を "選ぶ"。
    - よって Quest は固定データとして綺麗に正規化しておくと勝てる。
    """

    name = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=10, choices=QuestDifficulty.choices)
    category = models.CharField(max_length=10, choices=QuestCategory.choices)

    # 「一目で理解できる種目が嬉しい」→ description に回数/秒も入れる
    description = models.TextField(blank=True)

    # ポイントは難易度から算出でも良いが、将来の調整が楽なのでDBに持つ
    points = models.PositiveIntegerField(default=10)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quests_quest"
        indexes = [
            models.Index(fields=["difficulty", "category", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.difficulty}/{self.category})"


class DailyQuestSet(models.Model):
    """
    「今日チームに提示された4つ」を固定する箱。

    NOTE:
    - ここが無いと、"達成" 押した瞬間におすすめが変わったりして信用が壊れる。
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="daily_sets",
    )

    # チームのローカル日付（TIME_ZONE=Asia/Tokyo を前提に timezone.localdate()）
    date = models.DateField(default=timezone.localdate)

    # 今日の難易度（チームポイント/ランクなどから決定）
    difficulty = models.CharField(max_length=10, choices=QuestDifficulty.choices)

    # 発表映え用: "logic" or "ai"（AIをOFFにしても成立する）
    generated_by = models.CharField(max_length=10, choices=DailyGeneratedBy.choices, default=DailyGeneratedBy.LOGIC)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "quests_daily_set"
        constraints = [
            models.UniqueConstraint(fields=["team", "date"], name="uq_daily_set_team_date"),
        ]
        indexes = [
            models.Index(fields=["date", "team"]),
        ]

    def __str__(self) -> str:
        return f"DailyQuestSet(team={self.team_id}, date={self.date})"


class DailyQuestItem(models.Model):
    """
    DailyQuestSet に紐づく「4つのクエスト」。
    """

    daily_set = models.ForeignKey(
        DailyQuestSet,
        on_delete=models.CASCADE,
        related_name="items",
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.PROTECT,  # seedデータを消す事故を防ぐ
        related_name="daily_items",
    )

    # 並び順（AIっぽい演出で順序を変える等）
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "quests_daily_item"
        constraints = [
            models.UniqueConstraint(fields=["daily_set", "quest"], name="uq_daily_item_set_quest"),
        ]
        indexes = [
            models.Index(fields=["daily_set", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"DailyQuestItem(set={self.daily_set_id}, quest={self.quest_id})"


class QuestCompletion(models.Model):
    """
    ユーザーが「達成」ボタンを押したログ。

    NOTE:
    - 1ユーザーが同じDailyQuestItemを複数回達成できないよう UniqueConstraint。
    - チーム合計ポイント加算/ランク更新はサービス層で transaction で行うのが安全。
    """

    daily_item = models.ForeignKey(
        DailyQuestItem,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quest_completions",
    )

    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "quests_completion"
        constraints = [
            models.UniqueConstraint(fields=["daily_item", "user"], name="uq_completion_dailyitem_user"),
        ]
        indexes = [
            models.Index(fields=["user", "completed_at"]),
        ]

    def __str__(self) -> str:
        return f"Completion(daily_item={self.daily_item_id}, user={self.user_id})"
