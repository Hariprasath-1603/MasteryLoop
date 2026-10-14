import json
import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import ResponseError

INTERACTION_STREAM_KEY = "masteryloop:interactions"

GROUP_KT_UPDATER = "group:kt_updater"
GROUP_LIVE_DASHBOARDS = "group:live_dashboards"
GROUP_INTEGRITY_SCANNER = "group:integrity_scanner"

CONSUMER_GROUPS = [
    GROUP_KT_UPDATER,
    GROUP_LIVE_DASHBOARDS,
    GROUP_INTEGRITY_SCANNER,
]


class InteractionEvent(BaseModel):
    """
    Contract schema for interaction events published onto Redis Streams.
    Decouples raw interaction capture from asynchronous downstream consumers.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    learner_id: UUID
    item_id: UUID
    session_id: UUID | None = None
    skill_ids: list[UUID]
    response: str | None = None
    correct: bool | None = None
    latency_ms: int | None = None
    scored: bool = True
    pilot: bool = False
    shown_at: datetime
    responded_at: datetime | None = None

    def to_redis_dict(self) -> dict[str, str]:
        """
        Serializes event attributes into a flat string-to-string dictionary
        required by Redis Streams (`XADD`).
        """
        payload: dict[str, str] = {
            "event_id": self.event_id,
            "learner_id": str(self.learner_id),
            "item_id": str(self.item_id),
            "session_id": str(self.session_id) if self.session_id else "",
            "skill_ids": json.dumps([str(s) for s in self.skill_ids]),
            "response": self.response if self.response is not None else "",
            "correct": "true"
            if self.correct is True
            else ("false" if self.correct is False else ""),
            "latency_ms": str(self.latency_ms) if self.latency_ms is not None else "",
            "scored": "true" if self.scored else "false",
            "pilot": "true" if self.pilot else "false",
            "shown_at": self.shown_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else "",
        }
        return payload

    @classmethod
    def from_redis_dict(
        cls, data: dict[str | bytes, str | bytes]
    ) -> "InteractionEvent":
        """
        Deserializes a Redis Stream entry (which may have byte or string keys/values)
        back into a strictly validated `InteractionEvent` instance.
        """
        decoded: dict[str, str] = {}
        for k, v in data.items():
            key_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            val_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            decoded[key_str] = val_str

        # Parse skill_ids JSON
        skill_ids_raw = decoded.get("skill_ids", "[]")
        skill_ids: list[UUID] = [UUID(s) for s in json.loads(skill_ids_raw)]

        # Parse booleans
        def parse_bool(val: str) -> bool | None:
            if not val:
                return None
            return val.lower() in ("true", "1")

        correct = parse_bool(decoded.get("correct", ""))
        scored_val = parse_bool(decoded.get("scored", "true"))
        scored = True if scored_val is None else scored_val
        pilot_val = parse_bool(decoded.get("pilot", "false"))
        pilot = False if pilot_val is None else pilot_val

        # Parse session_id
        session_id_raw = decoded.get("session_id")
        session_id = UUID(session_id_raw) if session_id_raw else None

        # Parse latencies
        latency_raw = decoded.get("latency_ms")
        latency_ms = int(latency_raw) if latency_raw else None

        # Parse datetimes
        shown_at = datetime.fromisoformat(decoded["shown_at"])
        responded_at_raw = decoded.get("responded_at")
        responded_at = (
            datetime.fromisoformat(responded_at_raw) if responded_at_raw else None
        )

        response = decoded.get("response") or None

        return cls(
            event_id=decoded.get("event_id", str(uuid.uuid4())),
            learner_id=UUID(decoded["learner_id"]),
            item_id=UUID(decoded["item_id"]),
            session_id=session_id,
            skill_ids=skill_ids,
            response=response,
            correct=correct,
            latency_ms=latency_ms,
            scored=scored,
            pilot=pilot,
            shown_at=shown_at,
            responded_at=responded_at,
        )


class InteractionStreamProducer:
    """Async producer for publishing interaction events to the event bus."""

    def __init__(
        self, redis_client: Redis, stream_key: str = INTERACTION_STREAM_KEY
    ) -> None:
        self.redis = redis_client
        self.stream_key = stream_key

    async def publish(self, event: InteractionEvent) -> str:
        """
        Publishes an interaction event to the stream.
        Returns the assigned Redis message ID.
        """
        entry_id = await self.redis.xadd(
            self.stream_key,
            event.to_redis_dict(),  # type: ignore[arg-type]
            maxlen=200000,
            approximate=True,
        )
        return (
            entry_id.decode("utf-8") if isinstance(entry_id, bytes) else str(entry_id)
        )


async def setup_stream_consumer_groups(
    redis_client: Redis,
    stream_key: str = INTERACTION_STREAM_KEY,
    groups: list[str] | None = None,
) -> None:
    """
    Idempotently creates required consumer groups for the interactions stream.
    Creates the stream if it does not already exist.
    """
    target_groups = groups or CONSUMER_GROUPS
    for group in target_groups:
        try:
            await redis_client.xgroup_create(
                name=stream_key,
                groupname=group,
                id="0",
                mkstream=True,
            )
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass  # Consumer group already exists
            else:
                raise
