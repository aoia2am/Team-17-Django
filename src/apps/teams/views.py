# src/apps/teams/views.py

"""
Teams Views（MVP）

このファイルは「画面制御のみ」を担当する。
- DB操作・ビジネスルールは services.py に集約されている
- views は Service を呼び、結果をテンプレートに渡す or リダイレクトするだけ

絶対ルール:
- Team / TeamMember / TeamInvite を直接操作しない
- 更新系は必ず TeamService を利用する

最低限のガード（views がやること）:
- 未所属ユーザーの導線（create/joinへ誘導）
- 所属不一致（URLのteam_idと自分の所属teamが違う）をブロック
- 破壊的操作は POST のみ（再生成/無効化）
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST

from typing import Optional

from .models import Team
from .services import TeamService
from django.shortcuts import get_object_or_404


service=TeamService()

# -----------------------------
# Helpers（共通ガード）
# -----------------------------


def _get_my_team_id_or_none(user) -> Optional[int]:

    """
    自分の所属チームIDを返す（未所属なら None）

    NOTE:
    - 参照のみ（更新しない）
    - TeamMember.user = OneToOne のため、user.team_membership が基本導線
    """
    membership = getattr(user, "team_membership", None)
    return membership.team_id if membership else None

def _redirect_to_team_entry(request, reason: Optional[str]=None):
    """
    未所属ユーザーを「作成 or 参加」導線へ誘導する。
    TODO（チーム方針でどちらに寄せるか決める）:
    - 最初は team_join に誘導する
    - あるいは onboarding（作る/参加する選択画面）へ誘導する
    """
    if reason:
        messages.info(request, reason)  # ← 注意: messages は request が必要。各viewで呼ぶ設計でもOK。
    return redirect("teams:join")


def _validation_error_to_message(e: ValidationError) -> str:
    # dict形式でもlist形式でも安定して人間向けメッセージにする
    if hasattr(e, "message_dict"):
        parts = []
        for field, msgs in e.message_dict.items():
            for m in msgs:
                parts.append(f"{field}: {m}" if field != "__all__" else str(m))
        return "\n".join(parts) if parts else "入力内容を確認してください"
    if hasattr(e, "messages") and e.messages:
        return "\n".join(e.messages)
    return str(e)


#----------
# Views
#----------

@login_required
def team_create_view(request):
    """
    チーム作成（1人チームは作成可能）

    仕様（MVP）:
    - GET:
        - チーム作成画面を表示
        - templates/onboarding/team_create.html
    - POST:
        - チーム名を受け取る
        - TeamService.create_team(owner=request.user, name=...)
        - 成功時:
            - チーム詳細 or ダッシュボードへリダイレクト
        - 失敗時:
            - ValidationError を捕捉
            - エラーメッセージを表示して同画面に戻す

    注意点:
    - チーム作成時、member_count=1（ownerのみ）
    - この時点ではクエストは未解放（2人以上で解放）

    # TODO:
    # - POST値: name
    # - try/except ValidationError
    # - messages.success / messages.error を適切に使う
    """
    # チーム新規作成画面
    # すでに所属している場合は詳細画面へ
    my_team_id=_get_my_team_id_or_none(request.user)
    if my_team_id:
        return redirect("teams:detail",team_id=my_team_id)
    
    if request.method=="POST":
        name=request.POST.get("name","")
        max_members_raw=request.POST.get("max_members","")  # 任意（フォームがあれば）
        max_members=5
        if max_members_raw:
            try:
                max_members=int(max_members_raw)
            except ValueError:
                messages.error(request,"max_membersは数値で入力してください。")
                return render(request,"onboarding/team_create.html")

        try:
            team = service.create_team(owner=request.user, name=name, max_members=max_members)
            messages.success(request, f"チーム「{team.name}」を作成しました！")
            return redirect("teams:detail", team_id=team.id)
        except ValidationError as e:
            messages.error(request, _validation_error_to_message(e))

    return render(request, "onboarding/team_create.html")


@login_required
def team_join_view(request):
    """
    チーム参加（招待コード）

    仕様（MVP）:
    - GET:
        - 招待コード入力画面を表示
        - templates/onboarding/team_join.html
    - POST:
        - 招待コードを受け取る（大文字化・trim）
        - TeamService.join_team_by_code(user=request.user, code=...)
        - 成功時:
            - チーム詳細 or ダッシュボードへリダイレクト
        - 失敗時:
            - ValidationError を捕捉
            - エラーメッセージ付きで同画面に戻す

    想定エラー:
    - 招待コードが無効 / 期限切れ
    - チームが満員
    - すでに別チームに所属している（1ユーザー=1チーム）

    # TODO:
    # - POST値: code
    # - service.join_team_by_code(...)
    # - messages.success / messages.error
    """
    # チーム参加画面
    my_team_id=_get_my_team_id_or_none(request.user)
    if my_team_id:
        return redirect("teams:detail",team_id=my_team_id)
    
    if request.method == "POST":
        code=request.POST.get("code","")
        try:
            result = service.join_team_by_code(user=request.user,code=code)
            messages.success(request,f"チーム「{result.team.name}」を参加しました！")
            return redirect("teams:detail",team_id=result.team.id)
        except ValidationError as e:
            messages.error(request, _validation_error_to_message(e))

    return render(request,"onboarding/team_join.html")

@login_required
def team_detail_view(request, team_id: int):

    """
    チーム詳細表示（ダッシュボード想定）

    仕様（MVP）:
    - GET:
        - チーム情報を表示
        - templates/teams/detail.html

    表示想定:
    - チーム名
    - メンバー一覧
    - member_count / max_members
    - クエスト解放状態:
        - team.is_quest_unlocked が True の場合のみ「クエスト」導線を表示

    注意点:
    - MVPでは「自分が所属しているチームのみ閲覧可能」を想定
    - 権限制御は必要最低限でOK（必要なら後続対応）

    # TODO:
    # - Team を取得（404考慮）
    # - request.user が所属しているチームかを確認
    # - context に team を渡す
    """

    my_team_id=_get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request,"チームに所属していません。")
    
    if my_team_id != team_id:
        messages.error(request,f"他のチームの情報は閲覧できません。")
        return redirect("teams:detail",team_id=my_team_id)

    team=get_object_or_404(Team,id=team_id, is_active=True)

    # 必要ならメンバー一覧もここで取る（readなのでOKとするなら）
    members=team.memberships.select_related("user").order_by("joined_at")
    return render(
        request,
        "teams/detail.html",
        {
            "team":team,
            "members":members,
            "invite":getattr(team,"invite",None)  # OneToOneなので無い場合がある
        }
    )

@login_required
@require_POST
def team_dissolve_view(request, team_id: int):
    """
    チーム解散（ownerのみ）
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "チームに所属していません。")

    if my_team_id != team_id:
        messages.error(request, "他のチーム操作はできません。")
        return redirect("teams:detail", team_id=my_team_id)

    try:
        service.dissolve_team(team_id=team_id, actor=request.user)
        messages.success(request, "チームを解散しました。")
        # 解散したので未所属 → join へ
        return redirect("teams:join")
    except ValidationError as e:
        messages.error(request, _validation_error_to_message(e))
        return redirect("teams:detail", team_id=team_id)
    except Exception:
        messages.error(request, "解散処理に失敗しました。もう一度お試しください。")
        return redirect("teams:detail", team_id=team_id)

@login_required
@require_POST
def invite_regenerate_view(request, team_id: int):
    """
    招待コード再生成

    仕様（MVP）:
    - POST のみ想定（ボタン押下）
    - TeamService.regenerate_invite(team_id=..., actor=request.user)
    - 成功時:
        - チーム詳細画面にリダイレクト
        - 「招待コードを再生成しました」メッセージ表示
    - 失敗時:
        - ValidationError（owner以外が実行 等）
        - エラーメッセージ表示して元画面へ

    注意点:
    - 実行可能なのは team.owner のみ
    - 招待コードはチームに1つ

    # TODO:
    # - service.regenerate_invite(...)
    # - messages.success / messages.error
    """
    my_team_id = _get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request, "チームに所属していません。")
    if my_team_id != team_id:
        messages.error(request, "他のチーム操作はできません。")
        return redirect("teams:detail", team_id=my_team_id)

    try:
        service.regenerate_invite(team_id=team_id, actor=request.user)
        messages.success(request, "招待コードを再生成しました。")
    except ValidationError as e:
        messages.error(request, _validation_error_to_message(e))

    return redirect("teams:detail", team_id=team_id)

@login_required
@require_POST
def invite_deactivate_view(request, team_id: int):
    """
    招待コード無効化（漏洩・荒らし対策）

    仕様（MVP）:
    - POST のみ想定
    - TeamService.deactivate_invite(team_id=..., actor=request.user)
    - 成功時:
        - チーム詳細へリダイレクト
        - 「招待コードを無効化しました」メッセージ表示

    補足:
    - MVPでは必須ではないが、将来の安全弁として用意
    - UI がなければ未使用でもOK

    # TODO:
    # - service.deactivate_invite(...)
    """
    my_team_id=_get_my_team_id_or_none(request.user)
    if my_team_id is None:
        return _redirect_to_team_entry(request,"チームに所属していません。")
    if my_team_id != team_id:
        messages.error(request,"他チームの操作はできません。")
        return redirect("teams:detail", team_id=my_team_id)

    try:
        service.deactivate_invite(team_id=team_id,actor=request.user)
        messages.success(request,"招待コードを無効化しました。")
    except ValidationError as e:
        messages.error(request, _validation_error_to_message(e))
    return redirect("teams:detail",team_id=team_id)