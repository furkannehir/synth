import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/synth")

    # Timeout so app starts quickly if Mongo is down
    MONGO_SERVER_SELECTION_TIMEOUT_MS = 10000

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 24))
    )

    # Invites
    INVITE_DEFAULT_EXPIRES_HOURS = int(os.getenv("INVITE_DEFAULT_EXPIRES_HOURS", 24))

    # LiveKit
    LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
    LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
    LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    LIVEKIT_HTTP_URL = os.getenv("LIVEKIT_HTTP_URL", "http://localhost:7881")

    # Media-server adapter to use ("livekit" by default)
    MEDIA_SERVER_ADAPTER = os.getenv("MEDIA_SERVER_ADAPTER", "livekit")

    # Frontend URL (used in password-reset email links)
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Resend (HTTP-based email — no SMTP port blocking)
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "Synth <onboarding@resend.dev>")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/synth_test")


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
