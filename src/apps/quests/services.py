# src/apps/quests/services.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction, models
from django.db.models import F, Min, Sum
from django.utils import timezone

from apps.notifications.services import NotificationService
from apps.teams.models import Team, TeamMember

from .models import (
    DailyQuestItem,
    DailyQuestSet,
    Quest,
    QuestCategory,
    QuestCompletion,
    QuestDifficulty,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


# ============================================================
# 設計ポリシー（重要）
# - views は DB を直接更新しない
# - quests ドメインの更新は、この QuestService に閉じ込める
# - 競合（同時達成/同時日次生成）を transaction + lock で吸収する
# ============================================================


@dataclass(frozen=True)
class TodaySetResult:
    """
    今日の4クエストを返すためのDTO。
    views 側で扱いやすい形にする。
    """
    daily_set: DailyQuestSet
    items: list[DailyQuestItem]
    generated_by: str  # "logic" or "ai"
    difficulty: str    # easy/medium/hard


@dataclass(frozen=True)
class CompleteResult:
    """
    complete() の返却用。
    views 側で flash message や表示更新に使う。
    """
    completion: QuestCompletion
    gained_points: int
    team_total_points: int
    rank_before: str
    rank_after: str

@dataclass(frozen=True)
class ProgressItem:
    daily_item: DailyQuestItem
    completed_count: int
    member_count: int
    is_completed_by_me: bool

@dataclass(frozen=True)
class TodayProgressResult:
    daily_set: DailyQuestSet
    items: list[ProgressItem]

@dataclass(frozen=True)
class TodayMvpResult:
    user: "AbstractUser" | None
    total_points: int
    first_completed_at: timezone.datetime | None
    daily_set: DailyQuestSet | None


class QuestService:
    """
    Questsドメインのサービス層。

    ここでやること（MVP）:
    1) 今日の4クエストの提示（DailyQuestSet を日付で固定）
    2) 達成（QuestCompletion を保存）
    3) チーム累計ポイント加算（Team.total_points）
    4) ランク更新（Team.rank）
    5) 通知連携（達成/ランクアップ）
    6) 進捗（各 item の達成人数）
    7) MVP（今日の合計pt最大、同点は最速）
    """

    def __init__(self) -> None:
        self.notification_service = NotificationService()

    # ------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------
    def assert_member(self, *, team_id: int, user: "AbstractUser") -> None:
        """
        user が team のメンバーであることを保証する（横読み防止）。
        """
        if not TeamMember.objects.filter(team_id=team_id, user=user).exists():
            raise ValidationError({"permission": "あなたはこのチームのメンバーではありません"})
    
    def assert_unlocked(self, *, team: Team) -> None:
        """
        要件: 2人以上でクエスト解放。
        """
        if not team.is_quest_unlocked:
            raise ValidationError({"unlock": "クエストは2人以上で解放されます（仲間を招待してください）"})

        if team.is_full and team.member_count > team.max_members:
            raise ValidationError({"team": "チーム人数が上限を超えています"})

    # ------------------------------------------------------------
    # Difficulty decision (Rank -> Difficulty)
    # ------------------------------------------------------------
    def decide_daily_difficulty_by_rank(self, *, team_rank: str) -> str:
        """
        ランク帯によって、その日に表示する難易度を決める。

        要件:
        - A,B => HARD
        - C,D => MEDIUM（※モデル上 normal ではなく medium）
        - E,F => EASY
        """
        rank = (team_rank or "F").upper()
        if rank in ("A", "B"):
            return QuestDifficulty.HARD
        if rank in ("C", "D"):
            return QuestDifficulty.MEDIUM
        return QuestDifficulty.EASY

    # ------------------------------------------------------------
    # Rank calculation (Total points -> Rank)
    # ------------------------------------------------------------
    def calculate_rank(self, *, total_points: int) -> str:
        """
        累計ポイントからランク（S〜F）を決める。

        要件をそのまま実装（※C→B以降は+500ずつ）
        - F -> E: 100
        - E -> D: 300
        - D -> C: 600
        - C -> B: 1100（600 + 500）
        - B -> A: 1600
        - A -> S: 2100
        """
        p = max(0, int(total_points))

        # 閾値（“到達したらそのランク以上”）
        # 例: p>=2100 => S
        thresholds = [
            ("S", 2100),
            ("A", 1600),
            ("B", 1100),
            ("C", 600),
            ("D", 300),
            ("E", 100),
            ("F", 0),
        ]
        for r, th in thresholds:
            if p >= th:
                return r
        return "F"

    # ------------------------------------------------------------
    # Today set (create or get)
    # ------------------------------------------------------------
    def get_or_create_today_set(self, *, team: Team, user: "AbstractUser") -> TodaySetResult:
        """
        「今日の4つ」を取得する。
        なければ生成して固定する（date単位で1つ）。

        仕様:
        - 日付が変われば別DailyQuestSetになる（= リセット）
        - AI/ロジックどちらでも、DailyQuestSetに固定して“おすすめが揺れない”ようにする
        """
        self.assert_member(team_id=team.id, user=user)
        self.assert_unlocked(team=team)

        today = timezone.localdate()  # JST想定（settings.TIME_ZONE が Asia/Tokyo ならOK）
        difficulty = self.decide_daily_difficulty_by_rank(team_rank=team.rank)

        # 既に今日のセットがあるならそれを返す
        qs = DailyQuestSet.objects.filter(team=team, date=today).first()
        if qs:
            items = list(
                DailyQuestItem.objects.filter(daily_set=qs)
                .select_related("quest", "daily_set")
                .order_by("sort_order")
            )
            return TodaySetResult(
                qs,
                items,
                qs.generated_by,
                qs.difficulty
            )

        # 無ければ生成（並行実行に備えて transaction / unique constraint を吸収）
        return self._create_today_set(team=team, today=today, difficulty=difficulty)

    @transaction.atomic
    def _create_today_set(self, *, team: Team, today, difficulty: str) -> TodaySetResult:
        """
        今日のDailyQuestSetを作成する（内部）。
        """
        # チーム行ロック（同日生成の競合を減らす）
        team = Team.objects.select_for_update().get(id=team.id)

        # 先にもう一度（競合で既にできた可能性）
        existing = DailyQuestSet.objects.filter(team=team, date=today).first()
        if existing:
            items = list(
                DailyQuestItem.objects.filter(daily_set=existing)
                .select_related("quest", "daily_set")
                .order_by("sort_order")
            )
            return TodaySetResult(existing, items, existing.generated_by, existing.difficulty)

        # 1) 4つ選ぶ（AI優先→失敗したらロジック）
        quests, generated_by = self._recommend_4_quests(team=team, difficulty=difficulty)

        # 2) DailyQuestSet 作成
        daily_set = DailyQuestSet.objects.create(
            team=team,
            date=today,
            difficulty=difficulty,
            generated_by=generated_by,
        )

        # 3) Item 作成（順番固定）
        items = [
            DailyQuestItem(daily_set=daily_set, quest=q, sort_order=i)
            for i, q in enumerate(quests)
        ]
        DailyQuestItem.objects.bulk_create(items)

        # 4) 取り直して返す（select_relatedで画面側が楽）
        saved_items = list(
            DailyQuestItem.objects.filter(daily_set=daily_set)
            .select_related("quest", "daily_set")
            .order_by("sort_order")
        )

        return TodaySetResult(daily_set, saved_items, generated_by, difficulty)

    # ------------------------------------------------------------
    # Recommend (AI with fallback)
    # ------------------------------------------------------------
    def _recommend_4_quests(self, *, team: Team, difficulty: str) -> tuple[list[Quest], str]:
        """
        今日の4つを選ぶ。

        方針:
        - 本命: AI（並び順/選定をAIに委ねる。integrations/openai に隔離）
        - 失敗時: ロジック（random + 2カテゴリ分散）
        """
        # --- AIルート（将来差し替え前提 / 今は失敗しても落ちない） ---
        if getattr(settings, "AI_ENABLED", False) and getattr(settings, "OPENAI_API_KEY", ""):
            try:
                # IMPORTANT:
                # - integrations/openai 側はあなたが実装担当とのことなので
                #   ここでは import を遅延させる（未実装でも起動できる）
                from integrations.openai.client import OpenAIClient  # type: ignore
                from integrations.openai.prompts import RECOMMEND_QUESTS_PROMPT  # type: ignore

                client = OpenAIClient(api_key=settings.OPENAI_API_KEY)

                # AIに渡す「最小で十分な情報」
                # - 候補クエストはDBの固定データ（生成AI地獄を回避）
                candidates = list(
                    Quest.objects.filter(difficulty=difficulty, is_active=True)
                    .only("id", "name", "difficulty", "category", "points", "description")
                )
                if len(candidates) < 4:
                    # 候補不足はロジックに落とす
                    raise RuntimeError("Not enough quests to recommend")

                payload = {
                    "team_rank": team.rank,
                    "team_total_points": team.total_points,
                    "difficulty": difficulty,
                    "candidates": [
                        {
                            "id": q.id,
                            "name": q.name,
                            "category": q.category,
                            "points": q.points,
                            "description": q.description,
                        }
                        for q in candidates
                    ],
                    # 10代向け/空気読み/やり過ぎない、などの思想は prompts 側へ
                }

                # AIは「idの配列」を返す想定（順序も含める）
                result = client.generate_json(prompt=RECOMMEND_QUESTS_PROMPT, data=payload)
                picked_ids = [int(x) for x in result.get("quest_ids", []) if str(x).isdigit()]
                
                # 4件に整える（足りなければロジック補完でもOKだが、まずは厳密に）
                if len(picked_ids) < 4:
                    raise RuntimeError("AI returned insufficient quest ids")

                picked = list(Quest.objects.filter(id__in=picked_ids, is_active=True))
                picked_map = {q.id: q for q in picked}
                ordered = [picked_map[qid] for qid in picked_ids if qid in picked_map][:4]

                if len(ordered) != 4:
                    raise RuntimeError("AI pick mismatch")

                return ordered, "ai"

            except Exception:
                # AIが落ちてもデモが落ちない：必ずロジックにフォールバック
                pass

        # --- ロジックルート（MVPの勝ち筋） ---
        return self._recommend_4_quests_logic(difficulty=difficulty), "logic"

    def _recommend_4_quests_logic(self, *, difficulty: str) -> list[Quest]:
        """
        疑似AI（ロジック）:
        - difficulty で絞る
        - stretch/muscle をなるべく混ぜる（発表映え + 飽き防止）
        """
        qs = Quest.objects.filter(difficulty=difficulty, is_active=True)
        if qs.count() < 4:
            raise ValidationError({"quest": "クエスト候補が不足しています（seedを投入してください）"})

        stretch = list(qs.filter(category=QuestCategory.STRETCH))
        muscle = list(qs.filter(category=QuestCategory.MUSCLE))
        allq = list(qs)

        picked: list[Quest] = []

        # できれば 2+2 に寄せる（足りない場合はある方から補う）
        random.shuffle(stretch)
        random.shuffle(muscle)

        picked.extend(stretch[:2])
        picked.extend(muscle[:2])

        # 4未満なら残りを全体から補完（重複除外）
        if len(picked) < 4:
            remain = [q for q in allq if q.id not in {x.id for x in picked}]
            random.shuffle(remain)
            picked.extend(remain[: 4 - len(picked)])

        # 念のため4に切る
        return picked[:4]

    # ------------------------------------------------------------
    # Complete (can complete all 4; daily reset; totals persist)
    # ------------------------------------------------------------
    @transaction.atomic
    def complete(self, *, user: "AbstractUser", daily_item_id: int) -> CompleteResult:
        """
        達成処理（MVPの肝）。

        要件:
        - 4つ全部達成OK（= daily_item ごとの重複だけ禁止）
        - 日付が変わればリセット（DailyQuestSet が date で固定）
        - 累計ポイント/ランクは Team に保持（Team.total_points / Team.rank）
        - 通知:
            - member_completed を作成
            - rank が上がったら team_rank_up も作成
        """
        # 1) daily_item を引く（teamも辿れるように）
        try:
            item = (
                DailyQuestItem.objects.select_related("daily_set", "quest", "daily_set__team")
                .get(id=daily_item_id)
            )
        except DailyQuestItem.DoesNotExist:
            raise ValidationError({"daily_item": "クエストが存在しません"})

        team: Team = item.daily_set.team

        # 2) 所属チェック（横読み防止）
        self.assert_member(team_id=team.id, user=user)
        self.assert_unlocked(team=team)

        # 3) 「今日のセット」以外は弾く（“日付変わればリセット”を厳密にする）
        today = timezone.localdate()
        if item.daily_set.date != today:
            raise ValidationError({"date": "このクエストは今日のものではありません（更新してください）"})

        # 4) 既に達成していたら “成功扱いで静かに戻す” のがUX良い
        #    UniqueConstraint で最終的に守られる
        try:
            completion = QuestCompletion.objects.create(daily_item=item, user=user, completed_at=timezone.now())
        except IntegrityError:
            # 連打/二重達成
            # ただし、UIでは「Quest Clear!!」を出したいなら views 側で分岐するため
            # ここは ValidationError にしてもOK。今回は“静かに成功”に寄せる。
            completion = QuestCompletion.objects.get(daily_item=item, user=user)

            # ポイント二重加算は絶対NGなので、ここで0を返す
            return CompleteResult(
                completion=completion,
                gained_points=0,
                team_total_points=team.total_points,
                rank_before=team.rank,
                rank_after=team.rank,
            )

        # 5) ポイント加算（Team累計に保持）
        #    同時達成があり得るので Team をロックして加算する
        team_locked = Team.objects.select_for_update().get(id=team.id)
        gained = int(item.quest.points)

        rank_before = team_locked.rank
        team_locked.total_points = int(team_locked.total_points) + gained

        # 6) ランク更新（必要なら）
        rank_after = self.calculate_rank(total_points=team_locked.total_points)
        if rank_after != team_locked.rank:
            team_locked.rank = rank_after

        team_locked.save(update_fields=["total_points", "rank", "updated_at"])

        # 7) 通知（達成）
        self.notification_service.create_member_completed(
            team=team_locked,
            actor=user,
            message=f"{getattr(user, 'display_name', 'メンバー')}さんが「{item.quest.name}」を達成！+{gained}pt",
        )

        # 8) 通知（ランクアップした時だけ）
        if rank_before != rank_after:
            self.notification_service.create_team_rank_up(
                team=team_locked,
                actor=None,
                message=f"チームランクが {rank_before} → {rank_after} に上がりました！",
            )

        return CompleteResult(
            completion=completion,
            gained_points=gained,
            team_total_points=team_locked.total_points,
            rank_before=rank_before,
            rank_after=rank_after,
        )
    
    # ------------------------------------------------------------
    # Progress (today)
    # ------------------------------------------------------------
    def get_today_progress(self, *, team: Team, user: "AbstractUser") -> TodayProgressResult:
        self.assert_member(team_id=team.id, user=user)
        self.assert_unlocked(team=team)

        today_set = self.get_or_create_today_set(team=team, user=user).daily_set

        items = list(
            DailyQuestItem.objects.filter(daily_set=today_set)
            .select_related("quest", "daily_set")
            .order_by("sort_order")
        )

        member_count = int(team.member_count)

        # 達成人数（itemごと）
        counts = {
            row["daily_item_id"]: int(row["c"])
            for row in (
                QuestCompletion.objects.filter(daily_item__in=items)
                .values("daily_item_id")
                .annotate(c=models.Count("id"))
            )
        }

        # 自分が達成済みか
        my_done_ids = set(
            QuestCompletion.objects.filter(daily_item__in=items, user=user).values_list("daily_item_id", flat=True)
        )

        progress_items: list[ProgressItem] = []
        for it in items:
            progress_items.append(
                ProgressItem(
                    daily_item=it,
                    completed_count=counts.get(it.id, 0),
                    member_count=member_count,
                    is_completed_by_me=(it.id in my_done_ids),
                )
            )

        return TodayProgressResult(daily_set=today_set, items=progress_items)
    
    # ------------------------------------------------------------
    # MVP (today)
    # ------------------------------------------------------------
    def get_today_mvp(self, *, team: Team, user: "AbstractUser") -> TodayMvpResult:
        self.assert_member(team_id=team.id, user=user)
        self.assert_unlocked(team=team)

        # 今日セットがないと集計できないので、存在保証（表示が揺れない）
        today_set = self.get_or_create_today_set(team=team, user=user).daily_set

        # 今日のこのチームの達成ログに限定
        qs = (
            QuestCompletion.objects.filter(daily_item__daily_set=today_set)
            .values("user_id")
            .annotate(
                total_points=Sum(F("daily_item__quest__points")),
                first_completed_at=Min("completed_at"),
            )
            .order_by("-total_points", "first_completed_at")
        )

        top = qs.first()
        if not top:
            return TodayMvpResult(user=None, total_points=0, first_completed_at=None, daily_set=today_set)
        
        # user取得（テンプレで表示できる形に）
        # ※ display_name を使う想定ならテンプレで getattr する
        from django.contrib.auth import get_user_model
        User = get_user_model()
        mvp_user = User.objects.filter(id=top["user_id"]).first()

        return TodayMvpResult(
            user=mvp_user,
            total_points=int(top["total_points"] or 0),
            first_completed_at=top["first_completed_at"],
            daily_set=today_set,
        )
