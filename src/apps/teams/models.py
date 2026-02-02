# src/apps/teams/models.py
from __future__ import annotations

import secrets
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_invite_code(length: int = 8) -> str:
    """
    招待コード生成（衝突しづらい）。
    NOTE: 8桁でも十分だが、万一の衝突には save() 側で再生成で対応する。
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Team(models.Model):
    """
    2〜5人のクローズドコミュニティ。

    NOTE:
    - member_countは集計値（キャッシュ）として持つと画面も速い。
    - total_points/rankも同様にキャッシュとして持つ（MVPが安定する）。
    """

    name = models.CharField(max_length=30)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_teams",
    )

    # MVP: 1チーム = 最大5人固定。将来のA/Bテストで変えたいなら max_members をモデルに持つ。
    max_members = models.PositiveSmallIntegerField(default=5)

    member_count = models.PositiveSmallIntegerField(default=1)  # owner を含む想定

    total_points = models.PositiveIntegerField(default=0)

    # ランク(S〜F): 表示用に確定値を持つ。更新はサービス層で一元化する。
    rank = models.CharField(max_length=1, default="F")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "teams_team"
        indexes = [
            models.Index(fields=["rank"]),
            models.Index(fields=["total_points"]),
        ]

    def clean(self):
        if self.max_members < 2 or self.max_members > 5:
            raise ValidationError("max_members must be between 2 and 5 for G-BASE MVP")

        if self.member_count > self.max_members:
            raise ValidationError("member_count cannot exceed max_members")

    def __str__(self) -> str:
        return f"Team({self.id}): {self.name}"

    @property
    def is_quest_unlocked(self) -> bool:
        """クエスト解放条件（2人以上）。"""
        return self.member_count >= 2

    @property
    def is_full(self) -> bool:
        return self.member_count >= self.max_members


class TeamInvite(models.Model):
    """
    チームの招待コード。

    方針:
    - コードはチームに1つで良い（再生成可能）。
    - 有効/無効や失効日時を持たせると運用が安定する。
    """

    team = models.OneToOneField(
        Team,
        on_delete=models.CASCADE,
        related_name="invite",
    )
    code = models.CharField(max_length=16, unique=True)

    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # MVPでは未使用でもOK

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "teams_invite"
        indexes = [
            models.Index(fields=["code"]),
        ]

    def __str__(self) -> str:
        return f"Invite({self.code}) for Team({self.team_id})"

    def regenerate(self):
        """
        招待コード再生成。
        NOTE: 「荒らし対策」や「漏洩時のリセット」に効く。
        """
        self.code = generate_invite_code()


class TeamMember(models.Model):
    """
    チーム所属（MVPでは 1ユーザー=1チーム を強制する）。

    実現方法:
    - user に UniqueConstraint を張ることで「複数チーム所属」を物理的に禁止。
    """

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.OneToOneField(  # ★ 1ユーザー=1チーム をDBレベルで強制
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_membership",
    )

    # 将来: 権限(OWNER/MEMBER) を追加しても良いが、MVPは owner はTeam.ownerで十分
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "teams_member"
        indexes = [
            models.Index(fields=["team", "joined_at"]),
        ]

    def __str__(self) -> str:
        return f"TeamMember(team={self.team_id}, user={self.user_id})"
