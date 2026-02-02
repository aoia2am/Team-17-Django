# src/apps/teams/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Team, TeamInvite, TeamMember, generate_invite_code

# --- typing ---------------------------------------------------------
# Pylance が get_user_model() の戻りを静的に追えないため、
# 型注釈は AbstractUser を使う（実行時は get_user_model() を使う）。
if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()


@dataclass(frozen=True)
class JoinResult:
    """
    join_team_by_code の返却用。
    views 側で「どのチームに入ったか」を確実に扱えるようにする。
    """
    team: Team
    membership: TeamMember

# -----------------------------
# Rank calculation (teams側の確定値)
# -----------------------------
# NOTE:
# - ランクは「累積ポイント total_points」から決まる“表示用スナップショット”
# - しきい値は MVP 仕様に合わせて固定
#
# 仕様（ユーザー提示）:
# F → E: 100
# E → D: 300
# D → C: 600
# C → B: 1100 (600 + 500)
# 以降 +500 ずつ加算（今回はMVPなので S までの代表値のみ用意）
RANK_THRESHOLDS = [
    ("F", 0),
    ("E", 100),
    ("D", 300),
    ("C", 600),
    ("B", 1100),
    ("A", 1600),
    ("S", 2100),
]

def calc_rank(total_points: int) -> str:
    """
    total_points から現在ランクを返す。
    NOTE: MVPではS以降を想定しないので、上限はSで固定。
    """
    if total_points is None:
        total_points = 0

    rank = "F"
    for r, threshold in RANK_THRESHOLDS:
        if total_points >= threshold:
            rank = r
    return rank


class TeamService:
    """
    Teamsドメインの更新処理を一元化するサービス。

    絶対ルール（views 側にも共有）:
    - Team / TeamMember / TeamInvite を直接更新せず、必ずこのサービス経由で操作する
    - member_count はキャッシュ値。TeamMember の増減と必ず同一トランザクションで整合を取る
    - 同時参加（競合）を考慮し、Team 行をロックして定員超過を防ぐ
    - total_points / rank もキャッシュ値（表示用の確定値）として team に持つ
    """

    # -----------------------------
    # Team creation
    # -----------------------------
    @transaction.atomic
    def create_team(self, *, owner: "AbstractUser", name: str, max_members: int = 5) -> Team:
        """
        チーム作成（owner で作成し、同時に TeamMember(owner) を作る）。

        成功後の状態:
        - Team.owner = owner
        - TeamMember が 1件（owner）
        - member_count = 1
        - TeamInvite が 1件（招待コード発行）
        """
        name = (name or "").strip()
        if not name:
            raise ValidationError({"name": "チーム名は必須です"})

        # max_members は 上限（2〜5の範囲で設定できる）
        # チームの現在人数は member_count（1〜max_members）
        # クエスト解放条件は member_count >= 2 の時

        if max_members < 2 or max_members > 5:
            raise ValidationError({"max_members": "max_members must be between 2 and 5 for G-BASE MVP"})

        # 1ユーザー=1チーム を DB が保証するが、メッセージを分かりやすくするため先にチェック
        if TeamMember.objects.filter(user=owner).exists():
            raise ValidationError({"user": "すでにチームに所属しています（1ユーザー=1チーム）"})

        team = Team.objects.create(
            name=name,
            owner=owner,  # 実行時は CustomUser インスタンス
            max_members=max_members,
            member_count=1,
            total_points=0,
            rank="F",
            is_active=True,
            dissolved_at=None,
        )

        # owner を所属させる（ここが MVP の前提）
        TeamMember.objects.create(team=team, user=owner)

        # 招待コード発行（衝突が起きたら数回リトライ）
        invite = TeamInvite(team=team, is_active=True)
        self._set_unique_invite_code(invite)
        invite.save()

        return team

    # -----------------------------
    # Joining
    # -----------------------------
    @transaction.atomic
    def join_team_by_code(self, *, user: "AbstractUser", code: str) -> JoinResult:
        """
        招待コードでチーム参加。

        仕様:
        - 招待コードは TeamInvite.code（unique）
        - invite.is_active = True が必須
        - expires_at が設定されている場合、期限内のみ
        - Team をロックして定員超過を防ぐ
        - 1ユーザー=1チーム（TeamMember.user OneToOne）違反は ValidationError に変換

        成功後:
        - TeamMember 作成
        - team.member_count を再計算して保存
        """
        code = (code or "").strip().upper()
        if not code:
            raise ValidationError({"code": "招待コードは必須です"})

        # invite を引く（存在しない / 無効なら弾く）
        try:
            invite = TeamInvite.objects.select_related("team").get(code=code)
        except TeamInvite.DoesNotExist:
            raise ValidationError({"code": "招待コードが無効です"})

        if not invite.is_active:
            raise ValidationError({"code": "この招待コードは無効化されています"})

        if invite.expires_at and invite.expires_at < timezone.now():
            raise ValidationError({"code": "この招待コードは期限切れです"})

        # Team 行をロック（同時参加で max_members を超えないように）
        team = Team.objects.select_for_update().get(id=invite.team_id)

        # チームが論理削除されているなら弾く
        if not team.is_active:
            raise ValidationError({"team": "このチームは解散されています"})


        # 自分がすでにどこかのチーム所属なら弾く
        if TeamMember.objects.filter(user=user).exists():
            raise ValidationError({"user": "すでにチームに所属しています（1ユーザー=1チーム）"})

        # 定員チェック（キャッシュ値より、真実の行数で見るのが安全）
        current_count = TeamMember.objects.filter(team=team).count()
        if current_count >= team.max_members:
            raise ValidationError({"team": "このチームは満員です"})

        # 参加（DBの OneToOne 制約で最終安全弁）
        try:
            membership = TeamMember.objects.create(team=team, user=user)
        except IntegrityError:
            # ほぼ「同時実行で user が別処理で所属した」ケース
            raise ValidationError({"user": "すでにチームに所属しています（1ユーザー=1チーム）"})

        # member_count を整合させる（真実に合わせる）
        self._recount_member_count(team)

        return JoinResult(team=team, membership=membership)

    #-------------------------------
    # チーム解散
    #-------------------------------

    @transaction.atomic
    def dissolve_team(self, *, team_id: int, actor):
        """
        チーム解散（論理削除）
        - owner のみ実行可
        """
        team = Team.objects.select_for_update().get(id=team_id)

        if team.owner_id != actor.id:
            raise ValidationError({"permission": "チームの解散はチーム作成者のみ可能です"})

        # 論理削除
        team.is_active = False
        team.dissolved_at = timezone.now()
        team.save(update_fields=["is_active", "dissolved_at", "updated_at"])

        #所属だけ外す
        TeamMember.objects.filter(team=team).delete()
        TeamInvite.objects.filter(team=team).update(is_active=False)

        # member_countも整合させる
        team.member_count = 0
        team.save(update_fields=["member_count", "updated_at"])

    # -----------------------------
    # Team points / rank (quests未整備でも作れる “受け皿”)
    # -----------------------------
    @transaction.atomic
    def add_points(self, *, team_id: int, delta: int, actor: "AbstractUser" | None = None, reason: str = "") -> Team:
        """
        チームの合計ポイントを加算し、ランクを更新する。

        方針:
        - 「ptが生まれる」のは quests 側だが、teams は “保持” を担当する
        - quests 完了処理からこのメソッドを呼ぶだけで良いようにしておく（後から差し替え可能）

        Args:
            team_id: 加算対象チーム
            delta: 加算ポイント（正の整数）
            actor: 将来監査ログを作るための引数（MVPでは未使用でもOK）
            reason: 将来監査ログを作るための引数（MVPでは未使用でもOK）
        """
        if delta <= 0:
            raise ValidationError({"points": "加算ポイントは正の値である必要があります"})

        team = Team.objects.select_for_update().get(id=team_id)

        team.total_points += int(delta)
        team.rank = calc_rank(team.total_points)

        team.save(update_fields=["total_points", "rank", "updated_at"])
        return team
    
    @transaction.atomic
    def recount_rank(self, *, team_id: int) -> Team:
        """
        total_points から rank を再計算して保存する（保守用）。
        """
        team = Team.objects.select_for_update().get(id=team_id)
        team.rank = calc_rank(team.total_points)
        team.save(update_fields=["rank", "updated_at"])
        return team


    # -----------------------------
    # Invite management
    # -----------------------------
    @transaction.atomic
    def regenerate_invite(self, *, team_id: int, actor: "AbstractUser") -> TeamInvite:
        """
        招待コード再生成。

        MVP 方針:
        - team に invite は1つ
        - 基本は owner のみ実行可（荒らし対策）
        """
        team = Team.objects.select_for_update().get(id=team_id)

        if not team.is_active:
            raise ValidationError({"team": "このチームは解散されています"})

        if team.owner_id != actor.id:
            raise ValidationError({"permission": "招待コードの再生成はチーム作成者のみ可能です"})

        invite, _ = TeamInvite.objects.get_or_create(
            team=team,
            defaults={"code": generate_invite_code(), "is_active": True},
        )

        invite.is_active = True
        invite.regenerate()
        self._set_unique_invite_code(invite)
        invite.save(update_fields=["code", "is_active", "updated_at"])

        return invite

    @transaction.atomic
    def deactivate_invite(self, *, team_id: int, actor: "AbstractUser") -> TeamInvite:
        """
        招待コードを無効化（漏洩時など）。

        MVP:
        - owner のみ
        """
        team = Team.objects.select_for_update().get(id=team_id)
        
        if not team.is_active:
            raise ValidationError({"team": "このチームは解散されています"})

        if team.owner_id != actor.id:
            raise ValidationError({"permission": "招待コードの無効化はチーム作成者のみ可能です"})

        invite, _ = TeamInvite.objects.get_or_create(
            team=team,
            defaults={"code": generate_invite_code(), "is_active": True},
        )
        invite.is_active = False
        invite.save(update_fields=["is_active", "updated_at"])
        return invite

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _recount_member_count(self, team: Team) -> None:
        """
        member_count を真実（TeamMember行数）に合わせて更新。
        """
        count = TeamMember.objects.filter(team=team).count()
        team.member_count = count
        team.save(update_fields=["member_count", "updated_at"])

    def _set_unique_invite_code(self, invite: TeamInvite, *, max_retry: int = 5) -> None:
        """
        招待コードの衝突を避けるため、DB存在確認しつつセットする。

        NOTE:
        - code は unique だが、生成衝突は理論上あり得るためガードする
        - max_retry を超えたら ValidationError
        """
        for _ in range(max_retry):
            code = generate_invite_code()
            if not TeamInvite.objects.filter(code=code).exists():
                invite.code = code
                return
        raise ValidationError({"code": "招待コード生成に失敗しました（再試行してください）"})
