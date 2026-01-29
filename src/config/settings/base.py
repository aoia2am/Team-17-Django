# src/config/settings/base.py
from pathlib import Path
import os

# base.py の位置: src/config/settings/base.py
# parents[0]=settings, [1]=config, [2]=src, [3]=repo_root(…/move-mate)
# 「manage.py がある src/」を BASE_DIR にしたいので parents[2] を採用する
BASE_DIR = Path(__file__).resolve().parents[2]  # => src/

# --------------------------------------------------------------------
# Security / Env
# --------------------------------------------------------------------
# .env は基本的にローカル専用。Git には載せない前提。
# ここでは「読み込み自体」は別途（python-dotenv等）に委ね、
# settings は環境変数が来る前提で書く（CI/CDでも使いやすい）。
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

# 本番は環境変数で "example.com,api.example.com" のように渡す想定
_raw_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [] if DEBUG else [h.strip() for h in _raw_hosts.split(",") if h.strip()]

# --------------------------------------------------------------------
# AI / OpenAI（integrations/openai で参照する設定）
# --------------------------------------------------------------------
# 方針:
# - APIキー・モデル・タイムアウト・リトライ・機能ON/OFFを settings に集約
# - views からは直接触らず、services -> integrations 経由で参照する

# AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# タイムアウトは短め推奨（Hackathonは「落ちない」優先）
# OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "15"))

# 失敗時のリトライ回数（課金・レート制限・体感待ち時間のバランス）
# OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

# 任意: 1日あたりの擬似トークン予算（超えたらAIを使わない運用）
# AI_DAILY_BUDGET_TOKENS = int(os.getenv("AI_DAILY_BUDGET_TOKENS", "20000"))


# --------------------------------------------------------------------
# Application definition
# --------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Project apps (src/apps/ 配下の各ディレクトリ apps.pyでの記述 [例]：src/apps/teams/app.py)
    "apps.accounts.apps.AccountsConfig",
    "apps.teams.apps.TeamsConfig",        
    "apps.quests.apps.QuestsConfig",
    "apps.notifications.apps.NotificationsConfig",
]

# --------------------------------------------------------------------
# Auth (Custom User)
# --------------------------------------------------------------------
# - カスタムUserを使う宣言。初回 migrate 前に必ず設定すること。
AUTH_USER_MODEL = "accounts.User"

# （任意）ログイン導線（Django標準のlogin_requiredなどが参照）
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# --------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------
# あなたの構造は src/templates/ を利用する前提なので DIRS に追加が必須
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # src/templates
        "APP_DIRS": True,                 # apps/*/templates も拾える（将来の拡張もOK）
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------
# Database
# --------------------------------------------------------------------
# あなたの構造では src/db.sqlite3
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --------------------------------------------------------------------
# Password validation
# --------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------
# i18n / timezone
# --------------------------------------------------------------------
LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------
# Static / Media
# --------------------------------------------------------------------
# あなたの構造では src/static/ と src/media/
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # src/static

# media は「将来使うために置いてある」でも、設定だけ入れておくのは害がない
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"  # src/media

# --------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
