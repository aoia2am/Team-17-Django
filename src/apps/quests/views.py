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

このviewsの狙い（後輩向け）:
- 「どのServiceを呼ぶか」「どうテンプレに渡すか」「エラー時どこへ戻すか」を理解する
- models を直接触らずに機能を成立させる（レイヤ分離の練習）
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

# TODO(後輩):
# - Team の参照（※更新はしない）
#   from apps.teams.models import Team
#
# - Serviceの利用（更新ロジックは service に閉じ込める）
#   from .services import QuestService
#   service = QuestService()

# TODO(後輩):
# templates:
# - templates/quests/today.html
#   context: team, daily_set, items, difficulty, generated_by
#
# - templates/quests/progress.html
#   context: team, daily_set, progress_items
#   progress_items は TodayProgressResult.items（ProgressItemの配列）
#   ProgressItem: daily_item / completed_count / member_count / is_completed_by_me
#
# - templates/quests/mvp.html
#   context: team, daily_set, mvp
#   mvp は TodayMvpResult（user/total_points/first_completed_at/daily_set）


# -----------------------------
# Helpers（teams と同じ思想）
# -----------------------------
def _get_my_team_id_or_none(user) -> int | None:
    """
    自分の所属チームIDを返す（未所属なら None）

    NOTE:
    - TeamMember.user = OneToOne のため、user.team_membership が基本導線
    - 参照のみ（更新しない）
    """
    membership = getattr(user, "team_membership", None)
    return membership.team_id if membership else None


def _redirect_to_team_entry(request, reason: str | None = None):
    """
    未所属ユーザーを「作成 or 参加」導線へ誘導する。
    quests はチーム前提なので、未所属が来たら teams:join に戻す。
    """
    if reason:
        messages.info(request, reason)
    return redirect("teams:join")


def _flash_validation_error(request, e: ValidationError, fallback: str):
    """
    ValidationError を flash message に落とすヘルパ。

    NOTE:
    - service は ValidationError({"unlock": "..."} ) のように dict を返すことがある
    - その場合、最初のメッセージだけ拾って表示する（MVPは簡潔でOK）
    """
    msg = fallback
    if hasattr(e, "message_dict") and e.message_dict:
        # e.message_dict: {"unlock": ["..."], ...}
        try:
            msg = next(iter(e.message_dict.values()))[0]
        except Exception:
            msg = fallback
    messages.error(request, msg)


# -----------------------------
# Views
# -----------------------------
@login_required
def today_view(request):
    """
    今日のクエスト表示（チーム単位 / 4件）。

    仕様（MVP）:
    - GET:
        1) request.user の所属チームを取得（未所属なら teams:join へ）
        2) QuestService.get_or_create_today_set(team=..., user=request.user)
           - 「日付が変わればリセット」= DailyQuestSet(date=今日) が無ければ作る
           - 「4つ全部達成OK」= 1日1回制限はかけない（Completion は item×user の重複防止のみ）
           - 「2人以上で解放」= 2人未満なら ValidationError({"unlock": ...})
        3) templates/quests/today.html に渡して表示

    UI要件:
    - クエストをタップ → Completed? Yes/No モーダル
      - Yes → POST /quests/complete/<daily_item_id>/
      - 成功したら flash message "Quest Clear!!"
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "クエストを見るには、まずチームに参加してください。")

    try:
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
        #     "difficulty": result.difficulty,     # "easy"/"medium"/"hard"
        #     "generated_by": result.generated_by, # "logic"/"ai"
        # }
        # return render(request, "quests/today.html", context)
        pass

    except ValidationError as e:
        # 代表例:
        # - unlock: 2人未満で解放されていない
        # - permission: 所属外アクセス（横読み防止）
        _flash_validation_error(request, e, "クエストを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)

    except Exception:
        # デモで落とさない（詳細はログに出す想定）
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)


@login_required
@require_POST
def complete_view(request, daily_item_id: int):
    """
    クエスト達成（モーダルの Yes → POST）。

    仕様（MVP）:
    - POST:
        1) 未所属なら teams:join へ
        2) QuestService.complete(user=request.user, daily_item_id=...)
           - 4つ全部達成OK
           - 既に達成済みなら gained_points=0 を返す（ポイント二重加算防止）
           - 2人未満なら unlock で ValidationError
        3) messages:
           - gained_points>0: success "Quest Clear!! +{pt}pt"
           - gained_points==0: info "達成済みです"
           - ランクアップがあれば info "Rank Up!! X → Y"
        4) quests:today へ戻す
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "達成するには、まずチームに参加してください。")

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
        pass

    except ValidationError as e:
        _flash_validation_error(request, e, "達成できませんでした。")
        return redirect("quests:today")

    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("quests:today")


@login_required
def progress_view(request):
    """
    チーム進捗（達成人数を星表示など）。

    仕様（MVP）:
    - GET:
        1) 未所属なら teams:join へ
        2) QuestService.get_today_progress(team=..., user=request.user)
           - 今日のセット（DailyQuestSet）を前提に、各 DailyQuestItem の達成人数を集計
           - ProgressItem を返す（completed_count / member_count / is_completed_by_me）
        3) templates/quests/progress.html に渡す

    表示要件:
    - 達成人数を星にして表示（例: 5人中3人なら ★★★☆☆）
      → テンプレ側で:
        stars_filled = completed_count
        stars_empty  = member_count - completed_count
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "進捗を見るには、まずチームに参加してください。")

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
        pass

    except ValidationError as e:
        _flash_validation_error(request, e, "進捗を表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)

    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)


@login_required
def mvp_view(request):
    """
    MVP表示（最もポイントを稼いだ人 / 同値は最速達成）。

    MVPの集計期間:
    - 「今日（DailyQuestSet.date=今日）」の合計ポイント

    仕様（MVP）:
    - GET:
        1) 未所属なら teams:join へ
        2) QuestService.get_today_mvp(team=..., user=request.user)
           - 今日の達成ログを集計
           - 合計ポイントが最大のユーザー
           - 同値の場合は最も早く達成したユーザー
        3) templates/quests/mvp.html に渡す

    NOTE:
    - まだ誰も達成していない日は mvp.user が None の想定
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "MVPを見るには、まずチームに参加してください。")

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
        pass

    except ValidationError as e:
        _flash_validation_error(request, e, "MVPを表示できませんでした。")
        return redirect("teams:detail", team_id=my_team_id)

    except Exception:
        messages.error(request, "予期しないエラーが発生しました。")
        return redirect("teams:detail", team_id=my_team_id)
