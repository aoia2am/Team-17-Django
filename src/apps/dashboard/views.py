# src/apps/dashboard/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render, get_object_or_404

from apps.teams.models import Team
from apps.quests.services import QuestService


# -----------------------------
# Service accessor
# -----------------------------
def _quest_service() -> QuestService:
    return QuestService()


# -----------------------------
# Helpers（teams/quests と同じ思想）
# -----------------------------
def _get_my_team_id_or_none(user) -> int | None:
    membership = getattr(user, "team_membership", None)
    return membership.team_id if membership else None


def _redirect_to_team_entry(request, reason: str | None = None):
    if reason:
        messages.info(request, reason)
    return redirect("teams:join")


def _flash_validation_error(request, e: ValidationError, fallback: str):
    msg = fallback
    if getattr(e, "message_dict", None):
        try:
            val = next(iter(e.message_dict.values()))
            msg = val[0] if isinstance(val, (list, tuple)) else str(val)
        except Exception:
            msg = fallback
    elif getattr(e, "messages", None):
        msg = e.messages[0]
    messages.error(request, msg)


# -----------------------------
# View
# -----------------------------
@login_required
def dashboard_index_view(request):
    """
    Dashboard（Home）:
    - Teamの概要（name/rank/pointsなど）
    - 今日のクエスト（4件）
    - 今日の進捗（★）
    - 今日のMVP
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "まずチームに参加してください。")

    team = get_object_or_404(Team, id=my_team_id, is_active=True)
    service = _quest_service()

    try:
        today = service.get_or_create_today_set(team=team, user=request.user)
        progress = service.get_today_progress(team=team, user=request.user)
        mvp = service.get_today_mvp(team=team, user=request.user)

        # -----------------------------
        # UI用の軽い整形（テンプレが楽）
        # -----------------------------
        # 例: 「今日の進捗」を★で表現したい場合
        # progress.items: list[ProgressItem]
        # ここでは「各クエストがチーム全員達成なら1スター」= 最大4スターにする例
        all_done_count = 0
        for p in progress.items:
            if p.member_count > 0 and p.completed_count >= p.member_count:
                all_done_count += 1
        stars_filled = all_done_count
        stars_total = 4

        context = {
            "team": team,

            # 今日のクエスト
            "daily_set": today.daily_set,
            "quest_items": today.items,
            "difficulty": today.difficulty,
            "generated_by": today.generated_by,

            # 進捗（詳細も渡す）
            "progress_items": progress.items,
            "stars_filled": stars_filled,
            "stars_total": stars_total,

            # MVP
            "mvp": mvp,
        }
        return render(request, "dashboard/index.html", context)

    except ValidationError as e:
        _flash_validation_error(request, e, "ダッシュボードを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)
