# src/apps/accounts/forms.py
from __future__ import annotations

from django import forms


class LoginForm(forms.Form):
    """
    ログイン用フォーム（email + password）

    NOTE:
    - 認証そのもの（authenticate/login）は views 側で行う
    - form は「入力の妥当性」と「エラーメッセージ」を担う
    """

    email = forms.EmailField(label="Email", max_length=254)
    password = forms.CharField(label="Password", widget=forms.PasswordInput)


class SignupForm(forms.Form):
    """
    新規登録用フォーム

    MVP:
    - email / display_name / password を登録
    - password 確認（password1/password2）を行う
    """

    email = forms.EmailField(label="Email", max_length=254)
    display_name = forms.CharField(label="Display name", max_length=30)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Password (again)", widget=forms.PasswordInput)

    def clean(self):
        """
        NOTE:
        - password一致チェックだけここで行う
        - email重複チェック等は views 側で User 作成時に弾く or ここで追加してもOK
        """
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned
