"""
Adapter factory — picks the concrete media-server implementation
based on the app's MEDIA_SERVER_ADAPTER config value.
"""

from flask import Flask

from app.ports.media_server import MediaServerPort


def create_media_server_adapter(app: Flask) -> MediaServerPort:
    """Instantiate the configured media-server adapter."""

    adapter_name = app.config.get("MEDIA_SERVER_ADAPTER", "livekit")

    if adapter_name == "livekit":
        from app.adapters.livekit_adapter import LiveKitAdapter

        return LiveKitAdapter(
            api_key=app.config["LIVEKIT_API_KEY"],
            api_secret=app.config["LIVEKIT_API_SECRET"],
            url=app.config["LIVEKIT_URL"],
            http_url=app.config["LIVEKIT_HTTP_URL"],
        )

    raise ValueError(f"Unknown media server adapter: {adapter_name}")
