# src/apps/quests/models.py
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class QuestDifficulty(models.TextChoices):
    # DB値は英語（easy/normal/hard）。表示ラベルも英語に統一。
    EASY = "easy", "Easy"
    MEDIUM = "normal", "Normal"
    HARD = "hard", "Hard"


class QuestCategory(models.TextChoices):
    # DB値は英語（stretch/muscle）。表示ラベルも英語に統一。
    STRETCH = "stretch", "Stretch"
    MUSCLE = "muscle", "Muscle"


# MVP仕様の固定ポイント
DEFAULT_POINTS_BY_DIFFICULTY: dict[str, int] = {
    QuestDifficulty.EASY: 10,
    QuestDifficulty.MEDIUM: 40,
    QuestDifficulty.HARD: 100,
}


class Quest(models.Model):
    """
    固定クエスト（DB seed 前提）。

    NOTE:
    - 「AI提案」は Quest を生成するのではなく、Quest を "選ぶ"。
    - よって Quest は固定データとして綺麗に正規化しておくと勝てる。

    MVP仕様:
    - points は difficulty と整合している必要がある（事故防止）
    easy=10 / medium=40 / hard=100
    """

    name = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=10, choices=QuestDifficulty.choices)
    category = models.CharField(max_length=10, choices=QuestCategory.choices)

    # 「一目で理解できる種目が嬉しい」→ 回数/秒などもここへ
    description = models.TextField(blank=True)

    # 将来調整の余地は残すが、MVPでは difficulty と一致させる（cleanでガード）
    points = models.PositiveIntegerField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quests_quest"
        indexes = [
            models.Index(fields=["difficulty", "category", "is_active"]),
        ]

    def clean(self):
        """
        MVPのバグ源を潰す（seed/管理画面/将来の手修正で points が壊れがち）。

        方針:
        - difficulty が決まっているなら points は固定値に一致させる
        - Hackathon中の「表示と加算がズレる」を物理的に防ぐ
        """
        expected = DEFAULT_POINTS_BY_DIFFICULTY.get(self.difficulty)
        if expected is not None and self.points != expected:
            raise ValidationError(
                {"points": f"points must be {expected} when difficulty='{self.difficulty}' (G-BASE MVP rule)"}
            )

    def __str__(self) -> str:
        return f"{self.name} ({self.difficulty}/{self.category})"


class DailyQuestSet(models.Model):
    """
    「今日チームに提示された4つ」を固定する箱。

    NOTE:
    - ここが無いと、"達成" 押した瞬間におすすめが変わる等で信用が壊れる。
    - 生成ロジック（疑似AI/AI）は service 層に隔離する。
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="daily_sets",
    )

    # JST想定なら localdate を使う（呼び出し側で date を渡し忘れる事故を防ぐ）
    date = models.DateField(default=timezone.localdate)

    # 今日の難易度（チームポイント/ランクなどから決定）
    difficulty = models.CharField(max_length=10, choices=QuestDifficulty.choices)

    # 発表映え用: "logic" or "ai"（AIをOFFにしても成立する）
    generated_by = models.CharField(max_length=10, default="logic")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quests_daily_set"
        constraints = [
            models.UniqueConstraint(fields=["team", "date"], name="uq_daily_set_team_date"),
        ]
        indexes = [
            models.Index(fields=["team", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self) -> str:
        return f"DailyQuestSet(team={self.team_id}, date={self.date}, diff={self.difficulty})"


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

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "quests_daily_item"
        constraints = [
            models.UniqueConstraint(fields=["daily_set", "sort_order"], name="uq_daily_item_set_sort"),
            models.UniqueConstraint(fields=["daily_set", "quest"], name="uq_daily_item_set_quest"),
        ]
        indexes = [
            models.Index(fields=["daily_set", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"DailyQuestItem(set={self.daily_set_id}, quest={self.quest_id}, order={self.sort_order})"


class QuestCompletion(models.Model):
    """
    ユーザーが「Completed? Yes」を選んだログ。

    NOTE:
    - 1ユーザーが同じDailyQuestItemを複数回達成できないよう UniqueConstraint。
    - チーム合計ポイント加算/ランク更新/MVP判定/通知作成は service 層で transaction で行うのが安全。

    追加要件との整合:
    - 星表示: DailyQuestItem.completions.count() で達成人数が取れる
    - MVP判定: userごとの points 合計は quest.points を join して集計できる
    同点なら「最も早い completed_at（min）」で勝者を決められる
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
