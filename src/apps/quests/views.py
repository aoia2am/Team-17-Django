# src/apps/quests/views.py
"""
Quests Views（MVP）

このファイルは「画面制御のみ」を担当する。
- DB操作・ビジネスルールは services.py に集約されている
- views は Service を呼び、結果をテンプレートに渡す or リダイレクトするだけ

絶対ルール:
- Quest / DailyQuestSet / DailyQuestItem / QuestCompletion を views で直接操作しない
- 更新系は必ず QuestService を利用する

最低限のガード（views がやること）:
- 未所属ユーザーは teams の entry（join/create）へ誘導する
- quests はチーム前提のため、未所属は来ないのが理想だが保険で守る
- 破壊的操作（達成）は POST のみ（@require_POST）
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST
from apps.teams.models import Team
from .services import QuestService


# -----------------------------
# Service accessor
# -----------------------------
def _service() -> QuestService:
    """
    Serviceを都度生成する（状態を持たせない前提でも、グローバル保持より安全）。
    """
    return QuestService()


# -----------------------------
# Helpers（teams と同じ思想で統一）
# -----------------------------


# リーダーのカンペに基づき Optional ではなく | None スタイルを適用
def _get_my_team_id_or_none(user) -> int | None:
    """
    自分の所属チームIDを返す（未所属なら None）
    """
    membership = getattr(user, "team_membership", None)
    return membership.team_id if membership else None


def _redirect_to_team_entry(request, reason: str | None = None):
    """
    未所属ユーザーを「作成 or 参加」導線へ誘導する。
    """
    if reason:
        messages.info(request, reason)
    return redirect("teams:join")


# リーダーが用意した統一エラー処理ヘルパーを採用
def _flash_validation_error(request, e: ValidationError, fallback: str):
    """
    ValidationError を flash message に落とすヘルパ。
    辞書形式の場合、最初のメッセージを優先的に拾う。
    """
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
# Views
# -----------------------------


@login_required
def today_view(request):
    """
    今日のクエスト表示（チーム単位 / 4件）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(
            request, "クエストを見るには、まずチームに参加してください。"
        )

    try:
        # あなたが実装したロジックを残しつつ、コメントアウトも維持
        # TODO(後輩):
        # 1) Team を参照で取得（更新はしない）
        # team = Team.objects.get(id=my_team_id)
        #
        # 2) service を呼ぶ（今日のセットを固定）
        # result = service.get_or_create_today_set(team=team, user=request.user)
        #
        # 3) テンプレに渡す（最低限）
        # context = {
        #     "team": team,
        #     "daily_set": result.daily_set,
        #     "items": result.items,               # DailyQuestItem の配列
        #     "difficulty": result.difficulty,     # "easy"/"NORMAL"/"hard"
        #     "generated_by": result.generated_by, # "logic"/"ai"
        # }
        # return render(request, "quests/today.html", context)
        team = get_object_or_404(Team, id=my_team_id)
        result = _service().get_or_create_today_set(team=team, user=request.user)

        context = {
            "team": team,
            "daily_set": result.daily_set,
            "items": result.items,
            "difficulty": result.difficulty,
            "generated_by": result.generated_by,
        }
        return render(request, "quests/today.html", context)

    except ValidationError as e:
        # リーダーのヘルパーに差し替え
        _flash_validation_error(request, e, "クエストを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)


@login_required
@require_POST
def complete_view(request, daily_item_id: int):
    """
    クエスト達成（モーダルの Yes → POST）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(
            request, "達成するには、まずチームに参加してください。"
        )

    try:
        # TODO(後輩):
        # result = service.complete(user=request.user, daily_item_id=daily_item_id)
        #
        # if result.gained_points > 0:
        #     messages.success(request, f"Quest Clear!! +{result.gained_points}pt")
        #     if result.rank_before != result.rank_after:
        #         messages.info(request, f"Team Rank Up!! {result.rank_before} → {result.rank_after}")
        # else:
        #     messages.info(request, "このクエストは達成済みです。")
        #
        # return redirect("quests:today")
        result = _service().complete(user=request.user, daily_item_id=daily_item_id)

        if result.gained_points > 0:
            messages.success(request, f"Quest Clear! +{result.gained_points}pt")
            if result.rank_before != result.rank_after:
                messages.info(
                    request, f"Team Rank Up! {result.rank_before}→{result.rank_after}"
                )
        else:
            messages.info(request, "このクエストは達成済みです。")
        return redirect("quests:today")

    except ValidationError as e:
        _flash_validation_error(request, e, "達成できませんでした。")
        return redirect("quests:today")
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("quests:today")


@login_required
def progress_view(request):
    """
    チーム進捗
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(
            request, "進捗を見るには、まずチームに参加してください。"
        )

    try:
        # TODO(後輩):
        # team = Team.objects.get(id=my_team_id)
        # progress = service.get_today_progress(team=team, user=request.user)
        #
        # context = {
        #     "team": team,
        #     "daily_set": progress.daily_set,
        #     "progress_items": progress.items,  # ProgressItem の配列
        # }
        # return render(request, "quests/progress.html", context)
        team = get_object_or_404(Team, id=my_team_id, is_active=True)
        progress = _service().get_today_progress(team=team, user=request.user)

        context = {
            "team": team,
            "daily_set": progress.daily_set,
            "progress_items": progress.items,
        }
        return render(request, "quests/progress.html", context)

    except ValidationError as e:
        _flash_validation_error(request, e, "進捗を表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)


@login_required
def mvp_view(request):
    """
    MVP表示
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(
            request, "MVPを見るには、まずチームに参加してください。"
        )

    try:
        # TODO(後輩):
        # team = Team.objects.get(id=my_team_id)
        # mvp = service.get_today_mvp(team=team, user=request.user)
        #
        # context = {
        #     "team": team,
        #     "daily_set": mvp.daily_set,
        #     "mvp": mvp,  # TodayMvpResult
        # }
        # return render(request, "quests/mvp.html", context)
        team = get_object_or_404(Team, id=my_team_id)
        mvp = _service().get_today_mvp(team=team, user=request.user)

        context = {
            "team": team,
            "daily_set": mvp.daily_set,
            "mvp": mvp,
        }
        return render(request, "quests/mvp.html", context)

    except ValidationError as e:
        _flash_validation_error(request, e, "MVPを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)
    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)
