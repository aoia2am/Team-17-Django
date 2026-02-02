# src/apps/dashboard/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.teams.models import Team
from apps.quests.models import QuestCompletion
from apps.quests.services import QuestService


def _quest_service() -> QuestService:
    return QuestService()


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


def _next_rank_threshold(rank: str) -> int:
    """
    quests/services.py の calculate_rank() の閾値と整合する「次ランク到達ライン」。
    表示用（リングの 80/100pt の 100側）に使う。
    """
    r = (rank or "F").upper()
    table = {
        "F": 100,   # F->E
        "E": 300,   # E->D
        "D": 600,   # D->C
        "C": 1100,  # C->B
        "B": 1600,  # B->A
        "A": 2100,  # A
    }
    return table.get(r, 100)


@login_required
def dashboard_index_view(request):
    """
    Dashboard（Home）:
    - Team概要（name/rank/points）
    - 今日の進捗（★：今日1つでも達成したメンバー数）
    - 今日のMVP
    - 今日のクエスト4件（カード + 達成ボタン）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "まずチームに参加してください。")

    team = get_object_or_404(Team, id=my_team_id, is_active=True)
    service = _quest_service()

    try:
        # 1) 今日のセット（4件）
        today = service.get_or_create_today_set(team=team, user=request.user)
        quest_items = today.items  # DailyQuestItem の list

        # 2) 自分が達成済みの daily_item_id（CLEAR!表示用）
        my_done_ids = set(
            QuestCompletion.objects.filter(
                user=request.user,
                daily_item__in=quest_items,
            ).values_list("daily_item_id", flat=True)
        )

        # 3) ★仕様：今日、チーム内で「1つでも達成した人」の人数
        # 今日セットに紐づく達成ログから user を distinct で数える
        completed_count = (
            QuestCompletion.objects.filter(daily_item__daily_set=today.daily_set)
            .values("user_id")
            .distinct()
            .count()
        )

        # 4) MVP
        mvp = service.get_today_mvp(team=team, user=request.user)

        # 5) 次ランク閾値（リング表示用）
        next_rank_threshold = _next_rank_threshold(team.rank)

        context = {
            "team": team,

            # ---- ここが「後輩テンプレの変数名」に合わせた部分 ----
            "items": quest_items,                     # today_card.html が items を参照
            "my_done_ids": my_done_ids,               # today_card.html が参照
            "completed_count": completed_count,       # progress_star.html が参照
            "mvp": mvp,                               # mvp.html が参照
            "next_rank_threshold": next_rank_threshold,  # progress_bar.html が参照

            # 参考用に残す（使わなくてもOK）
            "daily_set": today.daily_set,
            "difficulty": today.difficulty,
            "generated_by": today.generated_by,
        }

        return render(request, "dashboard/index.html", context)

    except ValidationError as e:
        _flash_validation_error(request, e, "ダッシュボードを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)
