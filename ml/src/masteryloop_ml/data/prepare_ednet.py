import argparse
import glob
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("prepare_ednet")

ID_NAMESPACE = uuid.UUID("f0e1d2c3-b4a5-6789-0123-456789abcdef")


def to_deterministic_uuid(prefix: str, raw_id: Any) -> str:
    """Creates a deterministic UUIDv5 string from a raw identifier."""
    return str(uuid.uuid5(ID_NAMESPACE, f"{prefix}:{raw_id}"))


def load_params(params_path: str = "params.yaml") -> dict[str, Any]:
    """Loads ETL parameters from params.yaml if available."""
    if os.path.exists(params_path):
        with open(params_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("etl", {})
    return {}


def generate_synthetic_ednet_slice(
    num_learners: int = 500,
    num_items: int = 100,
    interactions_per_learner: int = 50,
    random_seed: int = 42,
) -> pl.DataFrame:
    """
    Generates a realistic synthetic fallback dataset replicating EdNet KT1 / ASSISTments
    interaction characteristics (25,000+ sequential responses, 500 learners, 100 items).
    """
    logger.info(
        "Generating synthetic EdNet KT1 dataset slice: %d learners, %d items, %d interactions/learner...",
        num_learners,
        num_items,
        interactions_per_learner,
    )
    rng = np.random.default_rng(random_seed)

    # Synthetic item parameters (2PL IRT)
    item_difficulties = rng.normal(loc=0.0, scale=1.0, size=num_items)
    item_discriminations = rng.uniform(low=0.7, high=1.8, size=num_items)
    skill_tags = [f"SKILL-{(i % 10):02d}" for i in range(num_items)]

    records = []
    base_timestamp = 1791960000000  # Epoch ms (~October 2026)

    for u_idx in range(num_learners):
        raw_uid = f"synthetic_u_{u_idx:04d}"
        learner_ability = rng.normal(loc=0.0, scale=1.0)
        curr_time = base_timestamp + u_idx * 1800000  # Spread arrival times

        # Select a sequence of items for this learner
        item_indices = rng.choice(
            num_items, size=interactions_per_learner, replace=True
        )

        for i_pos, i_idx in enumerate(item_indices):
            a = item_discriminations[i_idx]
            b = item_difficulties[i_idx]
            prob = 1.0 / (1.0 + np.exp(-a * (learner_ability - b)))
            correct = bool(rng.random() < prob)

            # Response latency in ms (lognormal distribution with realistic EdTech range)
            raw_latency = int(rng.lognormal(mean=8.6, sigma=0.6))  # median ~5.4s
            raw_latency = max(800, min(raw_latency, 120000))

            user_answer = "A" if correct else rng.choice(["B", "C", "D"])

            records.append(
                {
                    "user_id": raw_uid,
                    "problem_id": f"q_{i_idx:03d}",
                    "correct": correct,
                    "timestamp": curr_time,
                    "elapsed_time": raw_latency,
                    "skill_id": skill_tags[i_idx],
                    "user_answer": user_answer,
                }
            )
            # Advance time for next question: response time + reading/thinking pause
            curr_time += raw_latency + int(rng.uniform(3000, 15000))

    return pl.DataFrame(records)


def sanitize_interactions(
    df: pl.DataFrame,
    min_interactions_per_learner: int = 15,
    max_interactions_per_learner: int = 1000,
    max_latency_ms: int = 300000,
    deduplicate: bool = True,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """
    Sanitizes raw tabular interaction records into platform schema:
      - Drops missing responses/correctness
      - Caps extreme latencies
      - Deduplicates (learner_id, timestamp, item_id)
      - Filters learners with fewer than min_interactions_per_learner
      - Deterministically maps identifiers to UUIDv5
      - Chronologically sorts per learner
    """
    initial_rows = df.height

    # Column mapping resolution
    cols = df.columns
    col_map = {}
    for c in ["user_id", "userId", "student_id", "learner_id"]:
        if c in cols:
            col_map[c] = "user_id"
            break
    for c in ["problem_id", "question_id", "item_id", "problemId"]:
        if c in cols:
            col_map[c] = "item_id"
            break
    for c in ["correct", "is_correct", "correctness"]:
        if c in cols:
            col_map[c] = "correct"
            break
    for c in ["timestamp", "order_id", "ms_first_response", "start_time"]:
        if c in cols:
            col_map[c] = "timestamp"
            break
    for c in ["elapsed_time", "latency_ms", "time_taken", "response_time"]:
        if c in cols:
            col_map[c] = "latency_ms"
            break
    for c in ["skill_id", "skill_name", "skills"]:
        if c in cols:
            col_map[c] = "skill_id"
            break
    for c in ["user_answer", "response", "answer"]:
        if c in cols:
            col_map[c] = "response"
            break

    renamed = df.rename(col_map)

    # Drop nulls in essential fields
    cleaned = renamed.filter(
        pl.col("user_id").is_not_null()
        & pl.col("item_id").is_not_null()
        & pl.col("correct").is_not_null()
    )

    # Cast core columns
    cleaned = cleaned.with_columns(
        pl.col("user_id").cast(pl.Utf8),
        pl.col("item_id").cast(pl.Utf8),
        pl.col("correct").cast(pl.Boolean),
    )

    # Timestamp handling
    if "timestamp" in cleaned.columns:
        if cleaned["timestamp"].dtype == pl.Utf8:
            cleaned = cleaned.with_columns(
                pl.col("timestamp").str.to_datetime(strict=False)
            )
        elif cleaned["timestamp"].dtype in [pl.Int64, pl.Float64, pl.Int32]:
            cleaned = cleaned.with_columns(
                pl.from_epoch(pl.col("timestamp").cast(pl.Int64), time_unit="ms")
            )
    else:
        cleaned = cleaned.with_columns(
            pl.datetime(2026, 10, 14, 0, 0, 0).alias("timestamp")
        )

    # Latency sanitization
    if "latency_ms" in cleaned.columns:
        cleaned = cleaned.with_columns(
            pl.col("latency_ms")
            .cast(pl.Int32, strict=False)
            .fill_null(5000)
            .clip(lower_bound=100, upper_bound=max_latency_ms)
        )
    else:
        cleaned = cleaned.with_columns(pl.lit(5000).alias("latency_ms"))

    # Response handling
    if "response" in cleaned.columns:
        cleaned = cleaned.with_columns(
            pl.col("response").cast(pl.Utf8).str.slice(0, 1).fill_null("A")
        )
    else:
        cleaned = cleaned.with_columns(
            pl.when(pl.col("correct"))
            .then(pl.lit("A"))
            .otherwise(pl.lit("B"))
            .alias("response")
        )

    # Skill handling
    if "skill_id" not in cleaned.columns:
        cleaned = cleaned.with_columns(pl.lit("SKILL-DEFAULT").alias("skill_id"))

    # Map raw user_id and item_id to deterministic UUIDv5 strings
    users_unique = cleaned.select("user_id").unique()["user_id"].to_list()
    items_unique = cleaned.select("item_id").unique()["item_id"].to_list()
    skills_unique = cleaned.select("skill_id").unique()["skill_id"].to_list()

    user_map = {u: to_deterministic_uuid("learner", u) for u in users_unique}
    item_map = {i: to_deterministic_uuid("item", i) for i in items_unique}
    skill_map = {s: to_deterministic_uuid("skill", s) for s in skills_unique}

    cleaned = cleaned.with_columns(
        pl.col("user_id").replace(user_map).alias("learner_id"),
        pl.col("item_id").replace(item_map).alias("item_id"),
        pl.col("skill_id").replace(skill_map).alias("skill_uuid"),
    )

    # Deduplicate (learner_id, timestamp, item_id)
    if deduplicate:
        cleaned = cleaned.unique(
            subset=["learner_id", "timestamp", "item_id"], keep="first"
        )

    # Chronologically sort per learner
    cleaned = cleaned.sort(["learner_id", "timestamp"])

    # Filter learners with minimum interactions
    learner_counts = cleaned.group_by("learner_id").len()
    valid_learners = learner_counts.filter(
        (pl.col("len") >= min_interactions_per_learner)
        & (pl.col("len") <= max_interactions_per_learner)
    ).select("learner_id")

    filtered = cleaned.join(valid_learners, on="learner_id", how="inner")

    # Format output schema matching database interactions & KT sequence needs
    result = filtered.select(
        [
            pl.col("learner_id"),
            pl.col("item_id"),
            pl.col("timestamp").alias("shown_at"),
            pl.col("response"),
            pl.col("correct"),
            pl.col("latency_ms"),
            pl.lit(True).alias("scored"),
            pl.lit(False).alias("pilot"),
            pl.col("skill_uuid").alias("skill_id"),
        ]
    )

    metrics = {
        "raw_input_rows": initial_rows,
        "clean_output_rows": result.height,
        "unique_learners": result["learner_id"].n_unique(),
        "unique_items": result["item_id"].n_unique(),
        "mean_latency_ms": float(result["latency_ms"].mean() or 0.0),
        "mean_accuracy": float(result["correct"].mean() or 0.0),
    }

    return result, metrics


def run_pipeline(input_path: str, output_dir: str) -> None:
    """Entry point for the prepare_ednet DVC stage."""
    params = load_params()
    min_interactions = params.get("min_interactions_per_learner", 15)
    max_interactions = params.get("max_interactions_per_learner", 1000)
    max_latency = params.get("max_latency_ms", 300000)
    fallback_learners = params.get("synthetic_fallback_learners", 500)
    fallback_items = params.get("synthetic_fallback_items", 100)
    fallback_interactions = params.get("synthetic_interactions_per_learner", 50)
    deduplicate = params.get("deduplicate_timestamps", True)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    out_parquet = out_path / "interactions.parquet"
    out_metrics = out_path / "etl_metrics.json"

    in_dir = Path(input_path)
    raw_files = []
    if in_dir.exists():
        if in_dir.is_file():
            raw_files = [str(in_dir)]
        else:
            raw_files = glob.glob(str(in_dir / "*.csv")) + glob.glob(
                str(in_dir / "*.parquet")
            )

    if not raw_files:
        logger.info(
            "No raw dataset files found in '%s'. Generating synthetic fallback dataset (500 learners, 100 items)...",
            input_path,
        )
        raw_df = generate_synthetic_ednet_slice(
            num_learners=fallback_learners,
            num_items=fallback_items,
            interactions_per_learner=fallback_interactions,
        )
    else:
        logger.info("Reading %d raw files from %s...", len(raw_files), input_path)
        chunks = []
        for rf in raw_files:
            if rf.endswith(".parquet"):
                chunks.append(pl.read_parquet(rf))
            else:
                chunks.append(pl.read_csv(rf, ignore_errors=True))
        raw_df = pl.concat(chunks)

    processed_df, metrics = sanitize_interactions(
        raw_df,
        min_interactions_per_learner=min_interactions,
        max_interactions_per_learner=max_interactions,
        max_latency_ms=max_latency,
        deduplicate=deduplicate,
    )

    processed_df.write_parquet(out_parquet)
    with open(out_metrics, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    logger.info(
        "ETL complete. Wrote %d interactions to %s.", processed_df.height, out_parquet
    )
    logger.info("ETL Metrics: %s", metrics)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="EdNet KT1 / ASSISTments chunked ETL pipeline"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default="data/raw",
        help="Path to raw dataset folder or file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed",
        help="Target directory for processed files",
    )
    args = parser.parse_args()

    run_pipeline(args.input_path, args.output_dir)


if __name__ == "__main__":
    main()
