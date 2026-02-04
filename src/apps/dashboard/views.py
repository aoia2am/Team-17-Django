# src/apps/dashboard/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

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
    r = (rank or "F").upper()
    table = {
        "F": 100,
        "E": 300,
        "D": 600,
        "C": 1100,
        "B": 1600,
        "A": 2100,
    }
    return table.get(r, 100)


@login_required
def dashboard_index_view(request):
    """
    Dashboard（Home）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "まずチームに参加してください。")

    team = get_object_or_404(Team, id=my_team_id, is_active=True)
    service = _quest_service()

    # ★ 例外が起きても描画できる最低限の context を先に作る
    context = {
        "team": team,
        "items": [],
        "my_done_ids": set(),
        "completed_count": 0,
        "mvp": None,
        "next_rank_threshold": _next_rank_threshold(team.rank),
        "daily_set": None,
        "difficulty": None,
        "generated_by": None,

        # 未解放表示用
        "quest_locked": False,
        "quest_lock_reason": None,
    }

    # 未解放なら service を呼ばずに、そのまま描画
    # (assert_unlocked の ValidationError をそもそも発生させない)
    if not getattr(team, "is_quest_unlocked", True):
        context["quest_locked"] = True
        context["quest_lock_reason"] = "クエストは2人以上で解放されます（仲間を招待してください）"
        return render(request, "dashboard/index.html", context)

    try:
        # 1) 今日のセット
        today = service.get_or_create_today_set(team=team, user=request.user)
        quest_items = today.items

        # 2) 自分の達成済み
        my_done_ids = set(
            QuestCompletion.objects.filter(
                user=request.user,
                daily_item__in=quest_items,
            ).values_list("daily_item_id", flat=True)
        )

        # 3) ★ 今日1つでも達成した人数
        completed_count = (
            QuestCompletion.objects.filter(daily_item__daily_set=today.daily_set)
            .values("user_id")
            .distinct()
            .count()
        )

        # 4) MVP
        mvp = service.get_today_mvp(team=team, user=request.user)

        # context 更新（後輩テンプレ互換）
        context.update({
            "items": quest_items,
            "my_done_ids": my_done_ids,
            "completed_count": completed_count,
            "mvp": mvp,
            "daily_set": today.daily_set,
            "difficulty": today.difficulty,
            "generated_by": today.generated_by,
        })

    except ValidationError as e:
        # ★ 追加：unlock のときは「画面内表示」に回す
        md = getattr(e, "message_dict", None) or {}
        if "unlock" in md:
            val = md.get("unlock")
            msg = val[0] if isinstance(val, (list, tuple)) and val else str(val)
            context["quest_locked"] = True
            context["quest_lock_reason"] = msg
            messages.info(request, msg)
        else:
            _flash_validation_error(request, e, "ダッシュボードの一部を表示できませんでした。")

    except Exception:
        messages.error(request, "ダッシュボードの読み込みに失敗しました。")

    return render(request, "dashboard/index.html", context)