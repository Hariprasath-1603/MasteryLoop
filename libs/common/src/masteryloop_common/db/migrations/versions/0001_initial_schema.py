"""0001_initial_schema

Initial PostgreSQL schema migration for MasteryLoop:
- Enums (UserRole, ItemState, ItemOrigin, SessionKind, SessionStatus, ReviewActionType, IntegrityCaseKind, IntegrityCaseStatus)
- Relational tables with foreign keys and check constraints
- Partitioned append-only `interactions` table (monthly range partitions + default partition)
- PostgreSQL trigger `prevent_interactions_mutation` preventing UPDATE and DELETE on interactions

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-14 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Custom PostgreSQL Enums
    # -------------------------------------------------------------------------
    user_role_enum = postgresql.ENUM(
        "learner",
        "educator",
        "author",
        "psychometrician",
        "admin",
        name="user_role_enum",
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    item_state_enum = postgresql.ENUM(
        "draft",
        "screened",
        "in_review",
        "pilot",
        "calibrating",
        "active",
        "retired",
        "rejected",
        name="item_state_enum",
    )
    item_state_enum.create(op.get_bind(), checkfirst=True)

    item_origin_enum = postgresql.ENUM("human", "ai", name="item_origin_enum")
    item_origin_enum.create(op.get_bind(), checkfirst=True)

    session_kind_enum = postgresql.ENUM(
        "adaptive", "fixed", "practice", name="session_kind_enum"
    )
    session_kind_enum.create(op.get_bind(), checkfirst=True)

    session_status_enum = postgresql.ENUM(
        "active", "completed", "abandoned", name="session_status_enum"
    )
    session_status_enum.create(op.get_bind(), checkfirst=True)

    review_action_type_enum = postgresql.ENUM(
        "approve", "edit", "reject", name="review_action_type_enum"
    )
    review_action_type_enum.create(op.get_bind(), checkfirst=True)

    integrity_case_kind_enum = postgresql.ENUM(
        "rapid_guessing", "similarity", "accuracy_jump", name="integrity_case_kind_enum"
    )
    integrity_case_kind_enum.create(op.get_bind(), checkfirst=True)

    integrity_case_status_enum = postgresql.ENUM(
        "open", "reviewed", "dismissed", name="integrity_case_status_enum"
    )
    integrity_case_status_enum.create(op.get_bind(), checkfirst=True)

    # -------------------------------------------------------------------------
    # 2. Users Table
    # -------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "learner",
                "educator",
                "author",
                "psychometrician",
                "admin",
                name="user_role_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="learner",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # -------------------------------------------------------------------------
    # 3. Skills Table
    # -------------------------------------------------------------------------
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_skills_code", "skills", ["code"], unique=True)
    op.create_index("ix_skills_subject", "skills", ["subject"])

    # -------------------------------------------------------------------------
    # 4. Skill Edges Table (Acyclic Prerequisite DAG)
    # -------------------------------------------------------------------------
    op.create_table(
        "skill_edges",
        sa.Column(
            "prereq_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("prereq_id != skill_id", name="ck_skill_edges_no_self_loop"),
    )

    # -------------------------------------------------------------------------
    # 5. Items Table (Assessment Bank)
    # -------------------------------------------------------------------------
    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stem_md", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("key", sa.CHAR(1), nullable=False),
        sa.Column("rationale_md", sa.Text(), nullable=False),
        sa.Column(
            "skill_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column(
            "state",
            postgresql.ENUM(
                "draft",
                "screened",
                "in_review",
                "pilot",
                "calibrating",
                "active",
                "retired",
                "rejected",
                name="item_state_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "origin",
            postgresql.ENUM("human", "ai", name="item_origin_enum", create_type=False),
            nullable=False,
            server_default="human",
        ),
        sa.Column(
            "lineage",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("a", sa.Float(), nullable=True),
        sa.Column("b", sa.Float(), nullable=True),
        sa.Column("param_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "array_length(skill_ids, 1) BETWEEN 1 AND 3",
            name="ck_items_skill_ids_count",
        ),
        sa.CheckConstraint(
            "key IN ('A', 'B', 'C', 'D', 'E', 'F')", name="ck_items_key_valid"
        ),
    )
    op.create_index("ix_items_state", "items", ["state"])
    op.create_index(
        "ix_items_skill_ids_gin", "items", ["skill_ids"], postgresql_using="gin"
    )

    # -------------------------------------------------------------------------
    # 6. Item Parameter History Table
    # -------------------------------------------------------------------------
    op.create_table(
        "item_param_history",
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("a", sa.Float(), nullable=False),
        sa.Column("b", sa.Float(), nullable=False),
        sa.Column("n_responses", sa.Integer(), nullable=False),
        sa.Column("point_biserial", sa.Float(), nullable=True),
        sa.Column(
            "fitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------------------------------------------------------------
    # 7. Learners Table
    # -------------------------------------------------------------------------
    op.create_table(
        "learners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("cohort", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_learners_user_id", "learners", ["user_id"])
    op.create_index("ix_learners_cohort", "learners", ["cohort"])

    # -------------------------------------------------------------------------
    # 8. Classes Table
    # -------------------------------------------------------------------------
    op.create_table(
        "classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "educator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_classes_educator_id", "classes", ["educator_id"])

    # -------------------------------------------------------------------------
    # 9. Enrollments Table
    # -------------------------------------------------------------------------
    op.create_table(
        "enrollments",
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------------------------------------------------------------
    # 10. Sessions Table
    # -------------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "adaptive",
                "fixed",
                "practice",
                name="session_kind_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "completed",
                "abandoned",
                name="session_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_learner_id", "sessions", ["learner_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])

    # -------------------------------------------------------------------------
    # 11. Interactions Table (Partitioned by RANGE on shown_at)
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE interactions (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY,
            learner_id UUID NOT NULL REFERENCES learners(id) ON DELETE RESTRICT,
            item_id UUID NOT NULL REFERENCES items(id) ON DELETE RESTRICT,
            session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
            shown_at TIMESTAMPTZ NOT NULL,
            responded_at TIMESTAMPTZ,
            response CHAR(1),
            correct BOOLEAN,
            latency_ms INT,
            scored BOOLEAN NOT NULL DEFAULT TRUE,
            pilot BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (id, shown_at)
        ) PARTITION BY RANGE (shown_at);
    """)

    op.execute(
        "CREATE INDEX ix_interactions_learner_shown ON interactions (learner_id, shown_at);"
    )
    op.execute("CREATE INDEX ix_interactions_item_id ON interactions (item_id);")

    # Range partitions for months
    op.execute("""
        CREATE TABLE interactions_y2026m09 PARTITION OF interactions
        FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
    """)
    op.execute("""
        CREATE TABLE interactions_y2026m10 PARTITION OF interactions
        FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');
    """)
    op.execute("""
        CREATE TABLE interactions_y2026m11 PARTITION OF interactions
        FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');
    """)
    op.execute("""
        CREATE TABLE interactions_y2026m12 PARTITION OF interactions
        FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
    """)
    op.execute("""
        CREATE TABLE interactions_y2027m01 PARTITION OF interactions
        FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00');
    """)
    op.execute("""
        CREATE TABLE interactions_default PARTITION OF interactions DEFAULT;
    """)

    # Enforce strictly append-only immutability via PostgreSQL trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_interactions_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Interactions table is strictly append-only. UPDATE and DELETE operations are forbidden.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_prevent_interactions_mutation
        BEFORE UPDATE OR DELETE ON interactions
        FOR EACH ROW EXECUTE FUNCTION prevent_interactions_mutation();
    """)

    # -------------------------------------------------------------------------
    # 12. Mastery Table
    # -------------------------------------------------------------------------
    op.create_table(
        "mastery",
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("estimate", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(64), nullable=False),
    )

    # -------------------------------------------------------------------------
    # 13. Review Actions Table
    # -------------------------------------------------------------------------
    op.create_table(
        "review_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "action",
            postgresql.ENUM(
                "approve",
                "edit",
                "reject",
                name="review_action_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("diff", postgresql.JSONB(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_review_actions_item_id", "review_actions", ["item_id"])
    op.create_index("ix_review_actions_reviewer_id", "review_actions", ["reviewer_id"])

    # -------------------------------------------------------------------------
    # 14. Integrity Cases Table
    # -------------------------------------------------------------------------
    op.create_table(
        "integrity_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "rapid_guessing",
                "similarity",
                "accuracy_jump",
                name="integrity_case_kind_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "learner_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "session_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open",
                "reviewed",
                "dismissed",
                name="integrity_case_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_integrity_cases_kind", "integrity_cases", ["kind"])
    op.create_index("ix_integrity_cases_status", "integrity_cases", ["status"])

    # -------------------------------------------------------------------------
    # 15. Audit Log Table
    # -------------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])


def downgrade() -> None:
    # Drop trigger and function
    op.execute(
        "DROP TRIGGER IF EXISTS trg_prevent_interactions_mutation ON interactions;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_interactions_mutation();")

    # Drop partition tables and master
    op.execute("DROP TABLE IF EXISTS interactions_y2026m09 CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions_y2026m10 CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions_y2026m11 CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions_y2026m12 CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions_y2027m01 CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions_default CASCADE;")
    op.execute("DROP TABLE IF EXISTS interactions CASCADE;")

    # Drop tables
    op.drop_table("audit_log")
    op.drop_table("integrity_cases")
    op.drop_table("review_actions")
    op.drop_table("mastery")
    op.drop_table("sessions")
    op.drop_table("enrollments")
    op.drop_table("classes")
    op.drop_table("learners")
    op.drop_table("item_param_history")
    op.drop_table("items")
    op.drop_table("skill_edges")
    op.drop_table("skills")
    op.drop_table("users")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS integrity_case_status_enum;")
    op.execute("DROP TYPE IF EXISTS integrity_case_kind_enum;")
    op.execute("DROP TYPE IF EXISTS review_action_type_enum;")
    op.execute("DROP TYPE IF EXISTS session_status_enum;")
    op.execute("DROP TYPE IF EXISTS session_kind_enum;")
    op.execute("DROP TYPE IF EXISTS item_origin_enum;")
    op.execute("DROP TYPE IF EXISTS item_state_enum;")
    op.execute("DROP TYPE IF EXISTS user_role_enum;")
