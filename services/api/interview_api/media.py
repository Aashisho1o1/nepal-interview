"""Media transport adapter (LiveKit). Secrets stay here, server-side."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Protocol

from livekit import api

from .config import Settings

log = logging.getLogger("interview_api.media")


class MediaControl(Protocol):
    def mint_join_token(
        self, *, room: str, identity: str, name: str, session_id: str
    ) -> tuple[str, str]: ...
    async def delete_room(self, room: str) -> bool: ...
    async def list_rooms(self) -> list[str]: ...


class LiveKitMedia:
    """Short-lived, room-scoped join tokens that dispatch the interview agent."""

    TOKEN_TTL = timedelta(seconds=90)  # only needs to last until the student joins

    def __init__(self, s: Settings):
        if not (s.livekit_url and s.livekit_api_key and s.livekit_api_secret):
            raise RuntimeError("LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET are required")
        self.s = s

    def mint_join_token(self, *, room, identity, name, session_id):
        token = (
            api.AccessToken(self.s.livekit_api_key, self.s.livekit_api_secret)
            .with_identity(identity)
            .with_name(name)
            .with_ttl(self.TOKEN_TTL)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=False,
                    can_publish_sources=["microphone"],
                    can_update_own_metadata=False,
                )
            )
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=self.s.agent_name,
                            metadata=json.dumps({"session_id": session_id}),
                        )
                    ],
                    # student + agent + avatar
                    max_participants=3,
                    empty_timeout=30,
                    departure_timeout=10,
                )
            )
            .to_jwt()
        )
        return self.s.livekit_url, token

    async def delete_room(self, room: str) -> bool:
        lk = api.LiveKitAPI(self.s.livekit_url, self.s.livekit_api_key, self.s.livekit_api_secret)
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room))
            return True
        except api.TwirpError as e:
            if e.code == "not_found":
                return True
            log.warning("delete_room failed", extra={"room": room, "code": e.code})
            return False
        except Exception:
            log.warning("delete_room failed", extra={"room": room}, exc_info=True)
            return False
        finally:
            await lk.aclose()

    async def list_rooms(self) -> list[str]:
        lk = api.LiveKitAPI(self.s.livekit_url, self.s.livekit_api_key, self.s.livekit_api_secret)
        try:
            res = await lk.room.list_rooms(api.ListRoomsRequest())
            return [r.name for r in res.rooms if r.name.startswith(self.s.room_prefix)]
        finally:
            await lk.aclose()


class FakeMedia:
    """For tests and local UI work without LiveKit. Signs nothing usable."""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.rooms: set[str] = set()
        self.minted: list[dict] = []
        self.fail_delete = False

    def mint_join_token(self, *, room, identity, name, session_id):
        self.rooms.add(room)
        self.minted.append({"room": room, "identity": identity, "session_id": session_id})
        return "wss://fake.invalid", f"fake-token-for-{room}"

    async def delete_room(self, room: str) -> bool:
        if self.fail_delete:
            return False
        self.deleted.append(room)
        self.rooms.discard(room)
        return True

    async def list_rooms(self) -> list[str]:
        return sorted(self.rooms)
