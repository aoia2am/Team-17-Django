# src/apps/accounts/views.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect

from .forms import LoginForm, SignupForm
from .models import User

def login_view(request):
    """
    ログイン（email + password）

    仕様（MVP）:
    - GET: login画面を表示（templates/auth/login.html）
    - POST: email/password を検証し、成功ならログインしてトップへリダイレクト
    - 失敗時: エラーメッセージ付きで同画面に戻す

    # TODO:
    # - from .forms import LoginForm
    # - from django.contrib.auth import authenticate, login
    # - GET: form表示 / POST: form検証→authenticate→login→redirect
    """
    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]

        # USERNAME_FIELD = "email" のため username=email
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect("/")
        else:
            form.add_error(None, "メールアドレスまたはパスワードが正しくありません")

    return render(request, "auth/login.html", {"form": form})

def signup_view(request):
    """
    新規登録（email + password）

    仕様（MVP）:
    - GET: 登録画面を表示（templates/auth/signup.html）
    - POST: 入力値を検証し、ユーザー作成 → ログイン → トップへ
    - 失敗時: エラーメッセージ付きで同画面に戻す

    # TODO:
    # - from .forms import SignupForm
    # - form.is_valid()
    # - User.objects.create_user(...)
    # - login(request, user)
    """
    form = SignupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        display_name = form.cleaned_data["display_name"]
        password = form.cleaned_data["password1"]

        # email 重複チェック
        if User.objects.filter(email=email).exists():
            form.add_error("email", "このメールアドレスは既に登録されています")
        else:
            user = User.objects.create_user(
                email=email,
                password=password,
                display_name=display_name,
            )
            login(request, user)
            return redirect("/")

    return render(request, "auth/signup.html", {"form": form})

@login_required
@require_POST
def logout_view(request):
    """
    ログアウト

    仕様（MVP）:
    - POST（または GET）でログアウト処理を行う
    - ログアウト後は LOGIN_URL（/auth/login/）へリダイレクト
    - セッションを破棄するだけで、追加処理は行わない

    補足:
    - セキュリティ的には POST 推奨
    - MVPでは GET でも許容（要チーム方針確認）

    # TODO:
    # - from django.contrib.auth import logout
    # - logout(request)
    # - redirect(LOGOUT_REDIRECT_URL)
    """
    logout(request)
    return redirect("/auth/login/")
