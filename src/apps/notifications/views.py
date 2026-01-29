# src/apps/notifications/views.py
"""
Notifications Views（MVP）

このファイルは「画面制御のみ」を担当する。
- DB操作・ビジネスルールは services.py に集約されている
- views は Service を呼び、結果をテンプレートに渡す or リダイレクトするだけ

絶対ルール:
- Notification / NotificationRead を直接操作しない
- 更新系は必ず NotificationService を利用する

最低限のガード（views がやること）:
- 未所属ユーザーは teams の entry（join/create）へ誘導する
- 所属不一致（team_id が自分の所属チームと違う）をブロック
- 破壊的操作は POST のみ（既読化）
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

# TODO:
# - services を import して service を生成する（views は service を呼ぶだけ）
# from .services import NotificationService
# service = NotificationService()

# TODO:
# template:
# - templates/notifications/list.html （チーム通知フィード）
#   feed を回して表示する（is_read で未読バッジ等も可能）
#
# 想定 context:
# - {"feed": feed, "team_id": team_id}


# -----------------------------
# Helpers（共通ガード）
# -----------------------------
def _get_my_team_id_or_none(user) -> int | None:
    """
    自分の所属チームIDを返す（未所属なら None）

    NOTE:
    - 参照のみ（更新しない）
    - TeamMember.user = OneToOne のため、user.team_membership が基本導線
    """
    membership = getattr(user, "team_membership", None)
    return membership.team_id if membership else None


def _redirect_to_team_entry(request, reason: str | None = None):
    """
    未所属ユーザーを「作成 or 参加」導線へ誘導する。

    MVP方針:
    - notifications は「チーム前提」なので、未所属が来たら teams:join に戻す
    - UI上の導線で本来来ないのが理想だが、事故防止の保険としてここで守る
    """
    if reason:
        messages.info(request, reason)
    return redirect("teams:join")


def _guard_team_access(request, team_id: int) -> int:
    """
    notifications 画面の共通ガード。

    返り値:
    - my_team_id（= 自分の所属チームID）

    挙動:
    - 未所属なら ValidationError ではなく「呼び出し側で redirect」させたいので、
    ここでは None を返さず、未所属は ValidationError にしない（views が分岐しやすい形にする）
    → ただし実装をシンプルにするため、ここは「所属確認と不一致チェックだけ」を担う。

    NOTE:
    - 共同開発者が views を書くときに
    「未所属」「所属不一致」を同じ流れで処理できるようにする。
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        # 未所属は views 側で teams entry へ redirect したい（UXも良い）
        raise ValidationError({"team": "あなたはまだチームに所属していません"})

    if my_team_id != team_id:
        # 所属不一致（横読み防止）
        raise ValidationError({"permission": "あなたはこのチームの通知を閲覧できません"})

    return my_team_id


# -----------------------------
# Views
# -----------------------------
@login_required
def notification_list_view(request, team_id: int):
    """
    チーム通知フィードの表示。

    仕様（MVP）:
    - GET:
        - NotificationService.list_feed(team_id=..., user=request.user)
        - templates/notifications/list.html に渡して表示
    - 表示想定:
        - 新しい順の通知
        - 既読/未読の見た目（未読バッジの布石）
        - actor がいる場合は「誰が」も出す

    ガード（viewsがやる）:
    1) 未所属:
    - teams:join（または onboarding）に誘導
    2) 所属不一致:
    - messages.error を出して、自分のチームの通知へ戻す（UX優先）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "通知を見るには、まずチームに参加してください。")

    try:
        _guard_team_access(request, team_id)

        # TODO:
        # feed = service.list_feed(team_id=team_id, user=request.user)
        # context = {"feed": feed, "team_id": team_id}
        # return render(request, "notifications/list.html", context)

        # 仮置き（views 実装時に削除）
        return render(request, "notifications/list.html", {"feed": [], "team_id": team_id})

    except ValidationError:
        messages.error(request, "このページは閲覧できません。")
        # 自分の所属チームの通知へ戻す（ここが一番迷わない）
        return redirect("notifications:list", team_id=my_team_id)


@login_required
@require_POST
def notification_read_view(request, notification_id: int):
    """
    通知を1件既読にする。

    仕様（MVP）:
    - POST:
        - NotificationService.mark_read(notification_id=..., user=request.user)
        - 原則: 自分のチーム通知一覧へ戻す
        - （リファラに戻す設計でもOKだが、Hackathonでは一覧固定が安全）

    失敗時:
    - ValidationError（所属外アクセス/通知なし等）
    - messages.error で表示して一覧へ戻す

    NOTE:
    - notification_id だけなので、未所属ガードは「teams entryへ」でOK
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "通知を見るには、まずチームに参加してください。")

    try:
        # TODO:
        # service.mark_read(notification_id=notification_id, user=request.user)
        # return redirect("notifications:list", team_id=my_team_id)

        # 仮置き（views 実装時に削除）
        messages.success(request, "既読にしました（仮）")
        return redirect("notifications:list", team_id=my_team_id)

    except ValidationError:
        messages.error(request, "既読化に失敗しました。")
        return redirect("notifications:list", team_id=my_team_id)


@login_required
@require_POST
def notification_read_all_view(request, team_id: int):
    """
    チーム通知を全件既読にする（発表映え用・任意）。

    仕様（MVP）:
    - POST:
        - created_count = service.mark_all_read(team_id=..., user=request.user)
        - messages.success で「◯件既読」など出すと映える
        - 一覧へリダイレクト

    ガード:
    - 未所属なら teams:join へ redirect
    - 所属してるのに team_id が違うなら messages.error → 自分のチーム通知へ redirect
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "通知を見るには、まずチームに参加してください。")

    try:
        _guard_team_access(request, team_id)

        # TODO:
        # created_count = service.mark_all_read(team_id=team_id, user=request.user)
        # messages.success(request, f"{created_count}件を既読にしました")
        # return redirect("notifications:list", team_id=team_id)

        # 仮置き（views 実装時に削除）
        messages.success(request, "全件既読にしました（仮）")
        return redirect("notifications:list", team_id=team_id)

    except ValidationError:
        messages.error(request, "この操作は実行できません。")
        return redirect("notifications:list", team_id=my_team_id)
