"""Production website configuration and reset emails without sending mail."""
import re
import runpy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import mongomock
import pytest
from flask import Flask

from app.extensions import mongo
from app.models import user
from app.services import auth_service


def configurations(monkeypatch, frontend_url=None):
    # Read the actual config definitions without importing local .env secrets.
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    if frontend_url is not None:
        monkeypatch.setenv("FRONTEND_URL", frontend_url)
    return runpy.run_path(str(Path(__file__).parents[1] / "app" / "config.py"))


def test_production_defaults_to_the_public_domain_while_development_remains_local(monkeypatch):
    configs = configurations(monkeypatch)
    assert configs["ProductionConfig"].FRONTEND_URL == "https://synthapp.io"
    assert configs["DevelopmentConfig"].FRONTEND_URL == "http://localhost:5173"


def test_frontend_url_environment_override_is_preserved(monkeypatch):
    configs = configurations(monkeypatch, "https://selfhosted.example.com")
    assert configs["ProductionConfig"].FRONTEND_URL == "https://selfhosted.example.com"


@pytest.mark.parametrize("frontend_url", [None, "https://synthapp.io/", "https://selfhosted.example.com/chat/"])
def test_reset_email_links_point_to_the_configured_website_without_duplicate_slashes(monkeypatch, frontend_url):
    config = configurations(monkeypatch, frontend_url)["ProductionConfig"]
    db = mongomock.MongoClient(tz_aware=True).public_domain_tests
    monkeypatch.setattr(mongo, "db", db)
    uid = user.create("owner", "owner@example.test", "private-hash")
    sent = []
    monkeypatch.setattr(auth_service.resend, "api_key", "isolated-test-key")
    monkeypatch.setattr(auth_service.resend.Emails, "send", lambda message: sent.append(message))
    app = Flask(__name__)
    app.config.from_object(config)
    app.config["RESEND_API_KEY"] = "isolated-test-key"
    with app.app_context():
        auth_service.forgot_password("owner@example.test")
    assert len(sent) == 1
    link = re.search(r"https://[^\s]+/reset-password\?token=[^\s]+", sent[0]["text"]).group()
    parts = urlsplit(link)
    expected = (frontend_url or "https://synthapp.io").rstrip("/")
    assert link.startswith(expected + "/reset-password?token=")
    assert "//" not in parts.path
    assert "localhost" not in link
    raw_token = parse_qs(parts.query)["token"][0]
    import hashlib
    assert user.find_by_id(uid)["reset_token_hash"] == hashlib.sha256(raw_token.encode()).hexdigest()
