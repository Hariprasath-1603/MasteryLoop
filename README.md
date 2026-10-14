# MasteryLoop — Milestone 1 (M1)

Adaptive Assessment, Psychometrically-Validated AI Item Generation, and Learning Intelligence Platform.

## Milestone 1 Deliverables Overview

1. **Monorepo Scaffolding & Virtual Environment**:
   - Python 3.12 `uv` workspace layout connecting `libs/common` and `ml`.
2. **Infrastructure**:
   - Docker Compose running PostgreSQL 16 (partitioned interaction store), Redis 7 (AOF-enabled for event streams), Qdrant vector database, and MLflow tracking server.
3. **Database Schema & Migrations**:
   - Complete PostgreSQL schema implemented with SQLAlchemy 2.0 and Alembic.
   - Monthly range-partitioned `interactions` table.
   - PostgreSQL trigger `prevent_interactions_mutation()` enforcing strictly append-only capture.
4. **Curriculum Skill DAG Validator**:
   - NetworkX and graph cycle-detection engine guaranteeing zero circular prerequisites.
5. **Redis Stream Event Bus**:
   - Strict Pydantic v2 `InteractionEvent` contract with bidirectional serialization for consumer fan-out (`group:kt_updater`, `group:live_dashboards`, `group:integrity_scanner`).
6. **Idempotent Seed Loader**:
   - High school mathematics skill graph, items with 2PL parameters ($a, b$), users with RBAC, cohorts, classes, enrollments, and baseline mastery estimates.
7. **EdNet / ASSISTments ETL & Leakage-Safe Splits (DVC)**:
   - Polars/PyArrow streaming processor mapping raw interaction feeds to platform schema.
   - Learner-level train/val/test splitter guaranteeing zero learner overlap.

## Quickstart

```bash
# 1. Start Docker infrastructure
make up

# 2. Run Alembic migrations
make migrate

# 3. Seed database
make seed

# 4. Run ETL pipeline & splits
make etl

# 5. Run test suite
make test
```
