import os
from flask import Flask, send_from_directory
from flask_cors import CORS

from app.config import config_by_name
from app.extensions import mongo, jwt


def create_app(config_name: str | None = None) -> Flask:
    """Application factory."""

    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # ── OpenAPI / Swagger UI config ─────────────────────────
    app.config.setdefault("API_TITLE", "Synth API")
    app.config.setdefault("API_VERSION", "v1")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/")
    app.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "/docs")
    app.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )
    # JWT security scheme so "Authorize" button appears in Swagger UI
    app.config.setdefault("API_SPEC_OPTIONS", {
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Paste the JWT token returned by /api/auth/login",
                }
            }
        }
    })

    # ── Extensions ──────────────────────────────────────────
    CORS(app)

    # Append serverSelectionTimeoutMS to Mongo URI for fast fail
    timeout_ms = app.config.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", 3000)
    uri = app.config["MONGO_URI"]
    separator = "&" if "?" in uri else "?"
    app.config["MONGO_URI"] = f"{uri}{separator}serverSelectionTimeoutMS={timeout_ms}"

    mongo.init_app(app)
    jwt.init_app(app)

    # ── Media-server adapter ────────────────────────────────
    from app.adapters import create_media_server_adapter
    import app.extensions as ext
    try:
        ext.media_server = create_media_server_adapter(app)
        app.logger.info("Media-server adapter loaded: %s", app.config.get("MEDIA_SERVER_ADAPTER"))
    except Exception as exc:
        app.logger.warning(
            "Could not initialise media-server adapter: %s – voice features disabled.",
            exc,
        )

    # ── Blueprints (via flask-smorest Api) ──────────────────
    from app.routes import init_api
    init_api(app)

    # ── Error handlers ──────────────────────────────────────
    from pymongo.errors import ServerSelectionTimeoutError

    @app.errorhandler(ServerSelectionTimeoutError)
    def handle_db_error(error):
        return {"error": "Database unavailable. Please try again later."}, 503

    # ── Database indexes & seeding (idempotent) ─────────────────
    with app.app_context():
        try:
            from app.models.user import ensure_indexes as user_indexes
            from app.models.role import ensure_indexes as role_indexes
            from app.models.server import ensure_indexes as server_indexes
            from app.models.channel import ensure_indexes as channel_indexes
            from app.models.invite import ensure_indexes as invite_indexes
            user_indexes()
            role_indexes()
            server_indexes()
            channel_indexes()
            invite_indexes()

            # Only seed defaults when the DB is empty (first boot)
            if mongo.db.roles.count_documents({}, limit=1) == 0:
                from app.models.role import seed_defaults as seed_roles
                seed_roles()
                app.logger.info("Seeded default roles.")
            else:
                # Ensure built-in roles stay in sync with code changes
                from app.models.role import sync_default_roles
                sync_default_roles()

            if mongo.db.servers.count_documents({"is_default": True}, limit=1) == 0:
                from app.models.server import seed_default as seed_server
                seed_server()
                app.logger.info("Seeded default server.")

            from app.models.server import find_default as find_default_server
            from app.models.channel import seed_default_for_server
            default_server = find_default_server()
            if default_server:
                seed_default_for_server(str(default_server["_id"]))

            app.logger.info("Database indexes verified & seeding complete.")
        except Exception as exc:
            app.logger.warning(
                "Could not create DB indexes (is MongoDB running?): %s",
                type(exc).__name__,
            )

    # ── Health check ────────────────────────────────────────
    @app.route("/health")
    def health():
        return {"status": "ok"}

    # ── Presence sweep (background thread) ──────────────────
    import threading

    def _presence_sweep():
        """Periodically mark stale users offline."""
        import time
        while True:
            time.sleep(30)
            try:
                with app.app_context():
                    from app.services.presence_service import sweep_stale_users
                    swept = sweep_stale_users()
                    if swept:
                        app.logger.debug("Presence sweep: %d user(s) marked offline.", swept)
            except Exception:
                pass  # keep thread alive even if DB is temporarily unreachable

    sweep_thread = threading.Thread(target=_presence_sweep, daemon=True)
    sweep_thread.start()

    # ── Serve frontend SPA (production only) ────────────────
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static_frontend")
    if os.path.isdir(static_dir):
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_frontend(path):
            full = os.path.join(static_dir, path)
            if path and os.path.isfile(full):
                return send_from_directory(static_dir, path)
            return send_from_directory(static_dir, "index.html")

    return app
