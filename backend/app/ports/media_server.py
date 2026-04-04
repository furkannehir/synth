"""
Port (interface) for media-server operations.

Any concrete adapter (LiveKit, Janus, Twilio, …) must implement
every abstract method so that the rest of the application stays
completely decoupled from the vendor SDK.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Value objects returned by the port ──────────────────────


@dataclass
class TrackInfo:
    """A single published track (audio or video)."""
    sid: str
    name: str = ""
    kind: str = ""  # "audio" | "video"
    muted: bool = False
    source: str = ""  # "camera" | "microphone" | "screen_share" | "screen_share_audio"


@dataclass
class ParticipantInfo:
    """A user currently connected to a media room."""
    identity: str
    name: str = ""
    sid: str = ""
    state: str = ""  # e.g. "JOINED", "ACTIVE"
    metadata: str = ""
    tracks: list[TrackInfo] = field(default_factory=list)


@dataclass
class RoomInfo:
    """A media room managed by the server."""
    name: str
    sid: str = ""
    num_participants: int = 0
    max_participants: int = 0
    creation_time: int = 0
    metadata: str = ""


# ── Abstract port ──────────────────────────────────────────


class MediaServerPort(ABC):
    """
    Contract that every media-server adapter must fulfil.

    All methods are **synchronous** from the caller's perspective;
    adapters that wrap async SDKs must bridge internally.
    """

    # ── Token ──────────────────────────────────────────────

    @abstractmethod
    def generate_token(
        self,
        room_name: str,
        identity: str,
        name: str = "",
        *,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        """Return a short-lived JWT the client uses to connect."""
        ...

    # ── Room management ────────────────────────────────────

    @abstractmethod
    def create_room(
        self,
        name: str,
        *,
        empty_timeout: int = 300,
        max_participants: int = 0,
    ) -> RoomInfo:
        """Create (or ensure) a room exists and return its info."""
        ...

    @abstractmethod
    def delete_room(self, name: str) -> None:
        """Destroy a room, disconnecting everyone in it."""
        ...

    @abstractmethod
    def list_rooms(self) -> list[RoomInfo]:
        """Return every active room on the media server."""
        ...

    # ── Participant management ─────────────────────────────

    @abstractmethod
    def list_participants(self, room_name: str) -> list[ParticipantInfo]:
        """Return the participants currently in a room."""
        ...

    @abstractmethod
    def remove_participant(self, room_name: str, identity: str) -> None:
        """Forcibly disconnect a participant from a room."""
        ...

    @abstractmethod
    def mute_participant(
        self,
        room_name: str,
        identity: str,
        track_sid: str,
        *,
        muted: bool = True,
    ) -> None:
        """Server-side mute/unmute a specific track."""
        ...
