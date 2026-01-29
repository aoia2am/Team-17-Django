# src/apps/accounts/models.py
from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """
    メールログイン前提の UserManager.

    NOTE:
    - Hackathonでは「早く動く」が最優先です。
    - ただし将来の拡張（SNSログイン・プロフィール）を考えると
    Userを最初からカスタムにしておくのが事故が少ない。
    """

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("email is required")
        
        # 大文字小文字ブレを吸収（重複登録事故の予防）
        email = self.normalize_email(email).lower()

        user = self.model(email=email, **extra_fields)
        
        # MVPでメール+パスワードなら signup 側で必須にするのが安全
        # 将来的な話(今は不要)ですが、SNSログイン等を想定するなら None のとき unusable に寄せる
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)

        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if password is None:
            raise ValueError("Superuser must have a password.")

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    アプリのユーザー（10代想定）。

    MVP方針:
    - email をログインIDにする
    - display_name はUIで必須入力にしてOK（匿名性とチーム内体験のため）
    """

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=30)

    # 将来: アイコン等が欲しければ ImageField を足す（ただしHackathonは避けても良い）
    # avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # created_at は auto_now_add の方が「作成日時」として事故りにくい
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "accounts_user"
        indexes = [
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        # 匿名性重視なら display_name のみにしてもOK
        return f"{self.display_name} <{self.email}>"
