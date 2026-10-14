import polars as pl
import pytest
from masteryloop_ml.data.splits import split_learner_interactions


def test_zero_learner_leakage_across_splits() -> None:
    """
    Asserts that NO learner appears in more than one split (strictly disjoint learner sets).
    """
    # Create dataset with 100 learners, 10 interactions each
    records = []
    for u in range(100):
        uid = f"learner_{u:03d}"
        for i in range(10):
            records.append(
                {
                    "learner_id": uid,
                    "item_id": f"item_{i}",
                    "correct": True,
                }
            )
    df = pl.DataFrame(records)

    train_df, val_df, test_df = split_learner_interactions(
        df=df,
        train_ratio=0.80,
        val_ratio=0.10,
        test_ratio=0.10,
        seed=1337,
    )

    train_learners = set(train_df["learner_id"].unique().to_list())
    val_learners = set(val_df["learner_id"].unique().to_list())
    test_learners = set(test_df["learner_id"].unique().to_list())

    # Strict disjointness assertions
    assert train_learners.isdisjoint(val_learners), "Train and Val share learners!"
    assert train_learners.isdisjoint(test_learners), "Train and Test share learners!"
    assert val_learners.isdisjoint(test_learners), "Val and Test share learners!"

    # Total learners preserved
    assert len(train_learners | val_learners | test_learners) == 100
    assert len(train_learners) == 80
    assert len(val_learners) == 10
    assert len(test_learners) == 10

    # Row counts preserved
    assert train_df.height + val_df.height + test_df.height == df.height


def test_invalid_ratios_raise_error() -> None:
    """Verifies that split ratios not summing to 1.0 are rejected."""
    df = pl.DataFrame(
        {"learner_id": ["u1", "u2", "u3"], "correct": [True, False, True]}
    )
    with pytest.raises(ValueError) as exc_info:
        split_learner_interactions(df, train_ratio=0.7, val_ratio=0.1, test_ratio=0.1)
    assert "sum to 1.0" in str(exc_info.value)


def test_insufficient_learners_raise_error() -> None:
    """Verifies that fewer than 3 learners cannot produce a 3-way split."""
    df = pl.DataFrame({"learner_id": ["u1", "u2"], "correct": [True, False]})
    with pytest.raises(ValueError) as exc_info:
        split_learner_interactions(df, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1)
    assert "At least 3 distinct learners" in str(exc_info.value)
