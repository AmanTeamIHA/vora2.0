import json
import uuid
from datetime import timedelta

from livekit.api import AccessToken, VideoGrants
from livekit.protocol.room import RoomConfiguration


def mint_test_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> str:
    """Short-lived browser token. Room metadata is what the worker reads at join."""
    metadata = json.dumps({"tenant_id": str(tenant_id), "agent_id": str(agent_id)})
    return (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(RoomConfiguration(name=room, metadata=metadata, empty_timeout=300))
        .to_jwt()
    )
