import enum
import uuid
from datetime import datetime
from typing import Any

from masteryloop_common.db.base import Base
from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# ============================================================================
# Enums
# ============================================================================


class UserRole(str, enum.Enum):
    learner = "learner"
    educator = "educator"
    author = "author"
    psychometrician = "psychometrician"
    admin = "admin"


class ItemState(str, enum.Enum):
    draft = "draft"
    screened = "screened"
    in_review = "in_review"
    pilot = "pilot"
    calibrating = "calibrating"
    active = "active"
    retired = "retired"
    rejected = "rejected"


class ItemOrigin(str, enum.Enum):
    human = "human"
    ai = "ai"


class SessionKind(str, enum.Enum):
    adaptive = "adaptive"
    fixed = "fixed"
    practice = "practice"


class SessionStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class ReviewActionType(str, enum.Enum):
    approve = "approve"
    edit = "edit"
    reject = "reject"


class IntegrityCaseKind(str, enum.Enum):
    rapid_guessing = "rapid_guessing"
    similarity = "similarity"
    accuracy_jump = "accuracy_jump"


class IntegrityCaseStatus(str, enum.Enum):
    open = "open"
    reviewed = "reviewed"
    dismissed = "dismissed"


# ============================================================================
# Core Domain Models
# ============================================================================


class User(Base):
    """Platform identity table supporting RBAC."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=True),
        nullable=False,
        default=UserRole.learner,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Skill(Base):
    """Curriculum skill node in the knowledge DAG."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SkillEdge(Base):
    """Directed prerequisite relationship edge between skills in curriculum DAG."""

    __tablename__ = "skill_edges"
    __table_args__ = (
        CheckConstraint("prereq_id != skill_id", name="ck_skill_edges_no_self_loop"),
    )

    prereq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Item(Base):
    """Assessment item bank table with strict psychometric lifecycle tracking."""

    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_state", "state"),
        Index("ix_items_skill_ids_gin", "skill_ids", postgresql_using="gin"),
        CheckConstraint(
            "array_length(skill_ids, 1) BETWEEN 1 AND 3",
            name="ck_items_skill_ids_count",
        ),
        CheckConstraint(
            "key IN ('A', 'B', 'C', 'D', 'E', 'F')",
            name="ck_items_key_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    stem_md: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSONB, nullable=False)
    key: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    rationale_md: Mapped[str] = mapped_column(Text, nullable=False)
    skill_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    state: Mapped[ItemState] = mapped_column(
        Enum(ItemState, name="item_state_enum", native_enum=True),
        nullable=False,
        default=ItemState.draft,
    )
    origin: Mapped[ItemOrigin] = mapped_column(
        Enum(ItemOrigin, name="item_origin_enum", native_enum=True),
        nullable=False,
        default=ItemOrigin.human,
    )
    lineage: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    a: Mapped[float | None] = mapped_column(Float, nullable=True)  # 2PL Discrimination
    b: Mapped[float | None] = mapped_column(Float, nullable=True)  # 2PL Difficulty
    param_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exposure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ItemParamHistory(Base):
    """Historical record of IRT 2PL calibration runs for each item."""

    __tablename__ = "item_param_history"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    a: Mapped[float] = mapped_column(Float, nullable=False)
    b: Mapped[float] = mapped_column(Float, nullable=False)
    n_responses: Mapped[int] = mapped_column(Integer, nullable=False)
    point_biserial: Mapped[float | None] = mapped_column(Float, nullable=True)
    fitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Learner(Base):
    """Minors-safe pseudonymized learner registry."""

    __tablename__ = "learners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    cohort: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Class(Base):
    """Classroom roster unit owned by an educator."""

    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    educator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Enrollment(Base):
    """Association between classes and enrolled learners."""

    __tablename__ = "enrollments"

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Session(Base):
    """Assessment session state machine instance."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[SessionKind] = mapped_column(
        Enum(SessionKind, name="session_kind_enum", native_enum=True),
        nullable=False,
    )
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum", native_enum=True),
        nullable=False,
        default=SessionStatus.active,
        index=True,
    )
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Interaction(Base):
    """
    Append-only partitioned interaction feed capturing item presentations and responses.
    Partitioned by RANGE on shown_at.
    """

    __tablename__ = "interactions"
    __table_args__ = (
        PrimaryKeyConstraint("id", "shown_at"),
        Index("ix_interactions_learner_shown", "learner_id", "shown_at"),
        Index("ix_interactions_item_id", "item_id"),
        {"postgresql_partition_by": "RANGE (shown_at)"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(start=1, cycle=False),
        nullable=False,
    )
    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response: Mapped[str | None] = mapped_column(CHAR(1), nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pilot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Mastery(Base):
    """Real-time per-learner, per-skill knowledge tracing estimate."""

    __tablename__ = "mastery"

    learner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    estimate: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)


class ReviewAction(Base):
    """Subject matter expert review decisions for AI/human item proposals."""

    __tablename__ = "review_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[ReviewActionType] = mapped_column(
        Enum(ReviewActionType, name="review_action_type_enum", native_enum=True),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrityCase(Base):
    """Flagged anomaly cases (rapid guessing, answer similarity) for educator review."""

    __tablename__ = "integrity_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[IntegrityCaseKind] = mapped_column(
        Enum(IntegrityCaseKind, name="integrity_case_kind_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    learner_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    session_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[IntegrityCaseStatus] = mapped_column(
        Enum(IntegrityCaseStatus, name="integrity_case_status_enum", native_enum=True),
        nullable=False,
        default=IntegrityCaseStatus.open,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """Immutable audit trail for security and regulatory compliance."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
