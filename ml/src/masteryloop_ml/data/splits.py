import argparse
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("learner_splits")


def load_params(params_path: str = "params.yaml") -> dict[str, Any]:
    """Loads split configuration from params.yaml."""
    if os.path.exists(params_path):
        with open(params_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("splits", {})
    return {}


def split_learner_interactions(
    df: pl.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Partitions interaction logs at the learner level into strictly disjoint train/val/test splits.

    Guarantees:
      - Zero learner overlap: train, val, and test learner sets are mutually disjoint.
      - All interactions for a given learner stay together in that learner's assigned split.
      - Deterministic reproduction via numpy seed.
    """
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-4:
        raise ValueError(f"Split ratios must sum to 1.0; got {total_ratio:.4f}")

    unique_learners = df.select("learner_id").unique().to_series().to_list()
    num_learners = len(unique_learners)

    if num_learners < 3:
        raise ValueError(
            f"At least 3 distinct learners required to generate train/val/test splits; found {num_learners}"
        )

    # Deterministic learner-level shuffle
    rng = np.random.default_rng(seed)
    shuffled_learners = np.array(sorted(unique_learners))
    rng.shuffle(shuffled_learners)

    n_train = int(np.round(num_learners * train_ratio))
    n_val = int(np.round(num_learners * val_ratio))

    # Guard bounds so all splits have at least 1 learner
    n_train = max(1, min(n_train, num_learners - 2))
    n_val = max(1, min(n_val, num_learners - n_train - 1))

    train_uids = set(shuffled_learners[:n_train])
    val_uids = set(shuffled_learners[n_train : n_train + n_val])
    test_uids = set(shuffled_learners[n_train + n_val :])

    # Runtime leakage-safe assertions
    assert train_uids.isdisjoint(val_uids), (
        "Leakage error: train and val share learners!"
    )
    assert train_uids.isdisjoint(test_uids), (
        "Leakage error: train and test share learners!"
    )
    assert val_uids.isdisjoint(test_uids), "Leakage error: val and test share learners!"

    train_df = df.filter(pl.col("learner_id").is_in(train_uids))
    val_df = df.filter(pl.col("learner_id").is_in(val_uids))
    test_df = df.filter(pl.col("learner_id").is_in(test_uids))

    # Assert total interactions and total learners preserved
    assert train_df.height + val_df.height + test_df.height == df.height, (
        "Interaction row count mismatch across splits!"
    )
    assert len(train_uids) + len(val_uids) + len(test_uids) == num_learners, (
        "Learner count mismatch across splits!"
    )

    logger.info(
        "Learner Split Complete: %d total learners (%d total interactions)\n"
        "  - Train: %d learners (%.1f%%) | %d interactions\n"
        "  - Val:   %d learners (%.1f%%) | %d interactions\n"
        "  - Test:  %d learners (%.1f%%) | %d interactions",
        num_learners,
        df.height,
        len(train_uids),
        (len(train_uids) / num_learners) * 100,
        train_df.height,
        len(val_uids),
        (len(val_uids) / num_learners) * 100,
        val_df.height,
        len(test_uids),
        (len(test_uids) / num_learners) * 100,
        test_df.height,
    )

    return train_df, val_df, test_df


def run_splits(input_path: str, output_dir: str) -> None:
    """Executes the split_sequences pipeline stage."""
    params = load_params()
    seed = params.get("random_seed", 42)
    train_ratio = params.get("train_ratio", 0.70)
    val_ratio = params.get("val_ratio", 0.15)
    test_ratio = params.get("test_ratio", 0.15)

    logger.info("Loading interactions from %s...", input_path)
    df = pl.read_parquet(input_path)

    train_df, val_df, test_df = split_learner_interactions(
        df=df,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    train_df.write_parquet(out / "train.parquet")
    val_df.write_parquet(out / "val.parquet")
    test_df.write_parquet(out / "test.parquet")
    logger.info(
        "Saved split parquet files to %s (train.parquet, val.parquet, test.parquet)",
        out,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Leakage-safe learner-level train/val/test splitter"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default="data/processed/interactions.parquet",
        help="Path to interactions.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/splits",
        help="Output directory for split parquets",
    )
    args = parser.parse_args()

    run_splits(args.input_path, args.output_dir)


if __name__ == "__main__":
    main()
