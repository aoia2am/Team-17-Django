# src/apps/accounts/urls.py
from django.urls import path

"""
accounts app の URL 定義（入口だけ確定させる）

共同開発ルール:
- modelsとurlsを元に、viewsとformsを実装してください!! 
- エラーが起きないように下記はコメントアウト状態にしています
"""

app_name = "accounts"

urlpatterns = [
    # 認証系
    # path("login/", views.login_view, name="login")
    # path("signup/", views.signup_view, name="signup")
    # path("logout/", views.logout_view, name="logout")

    # onboarding
    # path("onboarding/welcome/", views.welcome, name="welcome")
]
