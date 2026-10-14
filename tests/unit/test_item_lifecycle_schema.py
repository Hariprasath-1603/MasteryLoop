import uuid
from datetime import UTC, datetime

from masteryloop_common.db.models import (
    IntegrityCaseKind,
    IntegrityCaseStatus,
    Item,
    ItemOrigin,
    ItemState,
    ReviewActionType,
    SessionKind,
    SessionStatus,
    UserRole,
)
from masteryloop_common.events import InteractionEvent


def test_item_state_and_origin_enums() -> None:
    """Validates that all expected lifecycle states and origins exist."""
    expected_states = {
        "draft",
        "screened",
        "in_review",
        "pilot",
        "calibrating",
        "active",
        "retired",
        "rejected",
    }
    actual_states = {s.value for s in ItemState}
    assert actual_states == expected_states

    expected_origins = {"human", "ai"}
    actual_origins = {o.value for o in ItemOrigin}
    assert actual_origins == expected_origins

    expected_roles = {"learner", "educator", "author", "psychometrician", "admin"}
    actual_roles = {r.value for r in UserRole}
    assert actual_roles == expected_roles

    expected_session_kinds = {"adaptive", "fixed", "practice"}
    actual_session_kinds = {k.value for k in SessionKind}
    assert actual_session_kinds == expected_session_kinds

    expected_session_statuses = {"active", "completed", "abandoned"}
    actual_session_statuses = {s.value for s in SessionStatus}
    assert actual_session_statuses == expected_session_statuses

    expected_review_actions = {"approve", "edit", "reject"}
    actual_review_actions = {a.value for a in ReviewActionType}
    assert actual_review_actions == expected_review_actions

    expected_integrity_kinds = {"rapid_guessing", "similarity", "accuracy_jump"}
    actual_integrity_kinds = {k.value for k in IntegrityCaseKind}
    assert actual_integrity_kinds == expected_integrity_kinds

    expected_integrity_statuses = {"open", "reviewed", "dismissed"}
    actual_integrity_statuses = {s.value for s in IntegrityCaseStatus}
    assert actual_integrity_statuses == expected_integrity_statuses


def test_item_instance_attributes() -> None:
    """Validates item construction and property mapping."""
    item_id = uuid.uuid4()
    skill_1 = uuid.uuid4()
    skill_2 = uuid.uuid4()

    item = Item(
        id=item_id,
        stem_md="Solve for $x$: $2x + 5 = 15$.",
        options={"A": "5", "B": "10", "C": "2", "D": "7"},
        key="A",
        rationale_md="Subtract 5: 2x = 10, divide by 2: x = 5.",
        skill_ids=[skill_1, skill_2],
        state=ItemState.active,
        origin=ItemOrigin.ai,
        a=1.45,
        b=-0.20,
    )

    assert item.id == item_id
    assert item.key == "A"
    assert len(item.skill_ids) == 2
    assert item.state == ItemState.active
    assert item.origin == ItemOrigin.ai
    assert item.a == 1.45
    assert item.b == -0.20


def test_interaction_event_redis_roundtrip() -> None:
    """
    Validates that InteractionEvent serializes to Redis string dict
    and reconstitutes back to exact typed fields without loss of precision.
    """
    event_id = str(uuid.uuid4())
    learner_id = uuid.uuid4()
    item_id = uuid.uuid4()
    session_id = uuid.uuid4()
    skill_1 = uuid.uuid4()
    skill_2 = uuid.uuid4()
    now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
    responded = datetime(2026, 10, 14, 12, 0, 6, 250000, tzinfo=UTC)

    original_event = InteractionEvent(
        event_id=event_id,
        learner_id=learner_id,
        item_id=item_id,
        session_id=session_id,
        skill_ids=[skill_1, skill_2],
        response="A",
        correct=True,
        latency_ms=6250,
        scored=True,
        pilot=False,
        shown_at=now,
        responded_at=responded,
    )

    # Serialize to Redis stream dict (string-to-string)
    redis_dict = original_event.to_redis_dict()
    assert isinstance(redis_dict, dict)
    for k, v in redis_dict.items():
        assert isinstance(k, str)
        assert isinstance(v, str)

    # Reconstitute from dict (simulating raw byte keys/values from redis-py)
    byte_dict = {k.encode("utf-8"): v.encode("utf-8") for k, v in redis_dict.items()}
    restored_event = InteractionEvent.from_redis_dict(byte_dict)

    assert restored_event.event_id == original_event.event_id
    assert restored_event.learner_id == original_event.learner_id
    assert restored_event.item_id == original_event.item_id
    assert restored_event.session_id == original_event.session_id
    assert restored_event.skill_ids == original_event.skill_ids
    assert restored_event.response == original_event.response
    assert restored_event.correct == original_event.correct
    assert restored_event.latency_ms == original_event.latency_ms
    assert restored_event.scored == original_event.scored
    assert restored_event.pilot == original_event.pilot
    assert restored_event.shown_at == original_event.shown_at
    assert restored_event.responded_at == original_event.responded_at
