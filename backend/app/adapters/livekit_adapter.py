"""
Concrete adapter that bridges the MediaServerPort to the LiveKit
Python server SDK (livekit-api).

Token generation is synchronous.
Room / participant management uses the async ``LiveKitAPI`` client,
so every call is wrapped with ``asyncio.run()`` to stay compatible
with Flask's synchronous request cycle.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from livekit import api as lk

from app.ports.media_server import (
    MediaServerPort,
    ParticipantInfo,
    RoomInfo,
    TrackInfo,
)


class LiveKitConnectionError(Exception):
    """Raised when the LiveKit server is unreachable."""
    pass


class LiveKitAdapter(MediaServerPort):
    """LiveKit implementation of :class:`MediaServerPort`."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        url: str,
        http_url: str = "",
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._url = url  # e.g. "ws://localhost:7880" or "wss://…"

        # HTTP endpoint for LiveKit server API (room/participant management).
        # Falls back to deriving from the WS URL if not explicitly provided.
        self._http_url = http_url or (
            url.replace("wss://", "https://").replace("ws://", "http://")
        )

    # ── helpers ────────────────────────────────────────────

    def _run_async(self, coro):
        """
        Run an async coroutine synchronously, safe under gevent workers.

        ``asyncio.run()`` internally calls ``asyncio.get_event_loop()`` and
        raises if a loop is already running.  Gevent monkey-patching makes
        every thread appear to have a running loop, so ``asyncio.run()``
        always fails under gevent Gunicorn workers.

        Instead we explicitly create a *new* event loop, run the coroutine to
        completion, and close it — all inside the current thread.  This is
        fully isolated from gevent's event loop.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        except (OSError, ConnectionError) as exc:
            raise LiveKitConnectionError(
                f"Cannot reach LiveKit server at {self._http_url}: {exc}"
            ) from exc
        except Exception as exc:
            if "ServerDisconnectedError" in type(exc).__name__ or "ClientError" in type(exc).__name__:
                raise LiveKitConnectionError(
                    f"LiveKit server disconnected ({self._http_url}): {exc}"
                ) from exc
            raise
        finally:
            loop.close()


    async def _room_op(self, callback):
        """Open a LiveKitAPI session, call *callback*, then close."""
        lkapi = lk.LiveKitAPI(
            self._http_url,
            api_key=self._api_key,
            api_secret=self._api_secret,
        )
        try:
            return await callback(lkapi)
        finally:
            await lkapi.aclose()

    # ── Token ──────────────────────────────────────────────

    def generate_token(
        self,
        room_name: str,
        identity: str,
        name: str = "",
        *,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        token = (
            lk.AccessToken(self._api_key, self._api_secret)
            .with_identity(identity)
            .with_name(name or identity)
            .with_grants(
                lk.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=can_publish,
                    can_subscribe=can_subscribe,
                )
            )
            .to_jwt()
        )
        return token

    # ── Room management ────────────────────────────────────

    def create_room(
        self,
        name: str,
        *,
        empty_timeout: int = 300,
        max_participants: int = 0,
    ) -> RoomInfo:
        async def _create(lkapi: lk.LiveKitAPI):
            room = await lkapi.room.create_room(
                lk.CreateRoomRequest(
                    name=name,
                    empty_timeout=empty_timeout,
                    max_participants=max_participants,
                )
            )
            return self._to_room_info(room)

        return self._run_async(self._room_op(_create))

    def delete_room(self, name: str) -> None:
        async def _delete(lkapi: lk.LiveKitAPI):
            await lkapi.room.delete_room(lk.DeleteRoomRequest(room=name))

        self._run_async(self._room_op(_delete))

    def list_rooms(self) -> list[RoomInfo]:
        async def _list(lkapi: lk.LiveKitAPI):
            resp = await lkapi.room.list_rooms(lk.ListRoomsRequest())
            return [self._to_room_info(r) for r in resp.rooms]

        return self._run_async(self._room_op(_list))

    # ── Participant management ─────────────────────────────

    def list_participants(self, room_name: str) -> list[ParticipantInfo]:
        async def _list(lkapi: lk.LiveKitAPI):
            resp = await lkapi.room.list_participants(
                lk.ListParticipantsRequest(room=room_name)
            )
            return [self._to_participant_info(p) for p in resp.participants]

        return self._run_async(self._room_op(_list))

    def remove_participant(self, room_name: str, identity: str) -> None:
        async def _remove(lkapi: lk.LiveKitAPI):
            await lkapi.room.remove_participant(
                lk.RoomParticipantIdentity(room=room_name, identity=identity)
            )

        self._run_async(self._room_op(_remove))

    def mute_participant(
        self,
        room_name: str,
        identity: str,
        track_sid: str,
        *,
        muted: bool = True,
    ) -> None:
        async def _mute(lkapi: lk.LiveKitAPI):
            await lkapi.room.mute_published_track(
                lk.MuteRoomTrackRequest(
                    room=room_name,
                    identity=identity,
                    track_sid=track_sid,
                    muted=muted,
                )
            )

        self._run_async(self._room_op(_mute))

    # ── Mapping helpers ────────────────────────────────────

    @staticmethod
    def _to_room_info(room) -> RoomInfo:
        return RoomInfo(
            name=room.name,
            sid=room.sid,
            num_participants=room.num_participants,
            max_participants=room.max_participants,
            creation_time=room.creation_time,
            metadata=room.metadata,
        )

    @staticmethod
    def _to_participant_info(p) -> ParticipantInfo:
        _SOURCE_MAP = {
            0: "unknown",
            1: "camera",
            2: "microphone",
            3: "screen_share",
            4: "screen_share_audio",
        }
        tracks = [
            TrackInfo(
                sid=t.sid,
                name=t.name,
                kind=("audio" if t.type == 1 else "video" if t.type == 2 else "unknown"),
                muted=t.muted,
                source=_SOURCE_MAP.get(t.source, "unknown"),
            )
            for t in p.tracks
        ]
        return ParticipantInfo(
            identity=p.identity,
            name=p.name,
            sid=p.sid,
            state=str(p.state),
            metadata=p.metadata,
            tracks=tracks,
        )
