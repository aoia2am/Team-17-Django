# src/apps/notifications/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Notification, NotificationRead, NotificationType

# --- typing ---------------------------------------------------------
# Pylance が get_user_model() の戻りを静的に追えない問題への対処は
# teams/services.py と同じ方針に揃える。
if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

from apps.teams.models import Team, TeamMember


@dataclass(frozen=True)
class FeedItem:
    """
    list_feed の返却用（views側で扱いやすくする）。

    NOTE:
    - ここでは Notification をそのまま返しても良いが、
    将来「表示用整形（AIメッセージ等）」を挟みたくなるためラップしておく。
    """
    notification: Notification
    is_read: bool


class NotificationService:
    """
    Notifications ドメインの更新処理を一元化するサービス。

    絶対ルール（views 側にも共有）:
    - Notification / NotificationRead を views で直接作らない
    - 既読や作成はサービス経由で統一（未読バッジ・二重登録対策）

    MVPでやること:
    - team の通知フィードを表示する
    - 既読（1件 / 全件）を付けられる
    - 「達成」「ランクアップ」などの通知を作れる（quests/teams から呼ばれる）

    AI導入（将来差し替え可能）:
    - AIは integrations/openai に隔離
    - ここでは「AIを呼ぶかどうか」の判断と、失敗時フォールバックを定義する
    """

    # -----------------------------
    # Guards（チーム所属チェック）
    # -----------------------------
    def assert_member(self, *, team_id: int, user: "AbstractUser") -> None:
        """
        user が team_id のメンバーであることを保証する。

        NOTE:
        - 共同開発で views が増えるほど、権限バグは起きやすい。
        - services に寄せておくと「どの画面でも同じ安全性」を担保できる。
        """
        if not TeamMember.objects.filter(team_id=team_id, user=user).exists():
            raise ValidationError({"permission": "あなたはこのチームのメンバーではありません"})

    # -----------------------------
    # Feed（一覧取得）
    # -----------------------------
    def list_feed(
        self,
        *,
        team_id: int,
        user: "AbstractUser",
        limit: int = 50,
    ) -> list[FeedItem]:
        """
        チームの通知フィードを取得する（新しい順）。

        仕様（MVP）:
        - チーム所属でない場合は ValidationError
        - NotificationRead を見て is_read を付与する
        """
        self.assert_member(team_id=team_id, user=user)

        qs = (
            Notification.objects.filter(team_id=team_id)
            .select_related("actor", "team")
            .order_by("-created_at")[:limit]
        )

        notifications = list(qs)
        if not notifications:
            return []

        read_ids = set(
            NotificationRead.objects.filter(
                user=user, notification_id__in=[n.id for n in notifications]
            ).values_list("notification_id", flat=True)
        )

        return [FeedItem(notification=n, is_read=(n.id in read_ids)) for n in notifications]

    # -----------------------------
    # Read（既読）
    # -----------------------------
    
    @transaction.atomic
    def mark_read(self, *, notification_id: int, user: "AbstractUser") -> None:
        try:
            n = Notification.objects.select_related("team").get(id=notification_id)
        except Notification.DoesNotExist:
            raise ValidationError({"notification": "通知が存在しません"})

        self.assert_member(team_id=n.team_id, user=user)

        try:
            NotificationRead.objects.create(notification=n, user=user, read_at=timezone.now())
        except IntegrityError:
            return

        

    @transaction.atomic
    def mark_all_read(self, *, team_id: int, user: "AbstractUser") -> int:
        """
        チームの通知を全件既読にする（発表映え用・任意）。

        仕様（MVP）:
        - チーム所属でない場合は ValidationError
        - すでに既読のものはスキップされる（bulk_create + ignore_conflicts）
        - 返り値: 新規に作成された既読件数（雑にでもUI表示に使える）
        """
        self.assert_member(team_id=team_id, user=user)

        ids = list(
            Notification.objects.filter(team_id=team_id).values_list("id", flat=True)
        )
        if not ids:
            return 0

        rows = [
            NotificationRead(notification_id=nid, user=user, read_at=timezone.now())
            for nid in ids
        ]

        # ignore_conflicts=True はDBにより挙動差があるが、SQLiteでも概ね動く
        created = NotificationRead.objects.bulk_create(rows, ignore_conflicts=True)
        return len(created)

    # -----------------------------
    # Create（通知作成）
    # -----------------------------
    def create_member_completed(
        self,
        *,
        team: Team,
        actor: "AbstractUser",
        message: Optional[str] = None,
    ) -> Notification:
        """
        「○○さんが達成しました」通知。

        NOTE:
        - message を外から渡せる形にしておくと、
        quests 側で文言を組み立てたい/AI差し替えしたい時に拡張しやすい。
        """
        if message is None:
            message = f"{getattr(actor, 'display_name', 'メンバー')}さんが達成しました"

        return Notification.objects.create(
            team=team,
            type=NotificationType.MEMBER_COMPLETED,
            message=message,
            actor=actor,
        )

    def create_team_rank_up(
        self,
        *,
        team: Team,
        actor: Optional["AbstractUser"] = None,
        message: Optional[str] = None,
    ) -> Notification:
        """
        チームランクアップ通知（quests/teams から呼ばれる想定）。
        """
        if message is None:
            message = f"チームランクが {team.rank} に上がりました！"

        return Notification.objects.create(
            team=team,
            type=NotificationType.TEAM_RANK_UP,
            message=message,
            actor=actor,
        )

    def create_daily_ready(
        self,
        *,
        team: Team,
        message: str,
        actor: Optional["AbstractUser"] = None,
    ) -> Notification:
        """
        今日のクエスト提示（朝/初回アクセス時など）。

        NOTE:
        - message は quests 側の結果を反映した文章にする想定
        """
        return Notification.objects.create(
            team=team,
            type=NotificationType.DAILY_READY,
            message=message,
            actor=actor,
        )

    # -----------------------------
    # AI comment（将来差し替え前提）
    # -----------------------------
    def build_team_mood_comment(
        self,
        *,
        team: Team,
        completed_count: int,
        member_count: int,
        difficulty: str,
    ) -> str:
        """
        チームの空気を読むコメント（AI導入ポイント①）。

        MVP方針:
        - まずは「疑似AI（ロジック）」で実装し、発表時にAI説明可能
        - 後で integrations/openai に差し替えられるよう、ここを窓口にする

        AI_ENABLED=false / API失敗時:
        - このロジック文言にフォールバックする（デモで落ちない）
        """
        # 1) まず疑似AI（テンプレ/分岐）で十分強い
        if member_count <= 0:
            return "今日も少しずつ積み上げよう"

        if completed_count >= member_count - 1 and member_count >= 2:
            return "あと1人で全員達成！誰か忘れてない？👀"
        if completed_count == 0:
            return "今日はちょっと静かだね。軽めのストレッチからいこう"
        if completed_count == 1 and member_count >= 4:
            return "1人目えらい。次いこう、空気作ろう。"

        # difficulty で雰囲気を微調整
        # 難易度はアプリの雰囲気に合わせて英語で!!
        if difficulty == "hard":
            return "今日は上級。無理せず、でも一歩だけ前へ。"
        if difficulty == "medium":
            return "中級いける日。フォーム意識していこう。"
        return "初級でもOK。続けた人が勝つ。"

    # 将来、integrations/openai を使うなら以下のような形で差し替える（今は未実装）
    # def build_team_mood_comment_ai(...):
    #     if not settings.AI_ENABLED or not settings.OPENAI_API_KEY:
    #         return self.build_team_mood_comment(...)
    #     try:
    #         from integrations.openai.client import OpenAIClient
    #         from integrations.openai.prompts import TEAM_MOOD_PROMPT
    #         client = OpenAIClient(...)
    #         return client.generate(...)
    #     except Exception:
    #         return self.build_team_mood_comment(...)
