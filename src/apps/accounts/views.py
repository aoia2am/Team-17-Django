# src/apps/accounts/views.py

def login_view(request):
    """
    ログイン（email + password）

    仕様（MVP）:
    - GET: login画面を表示（templates/auth/login.html）
    - POST: email/password を検証し、成功ならログインしてトップへリダイレクト
    - 失敗時: エラーメッセージ付きで同画面に戻す
    """
    pass
