"""Benford's law check on the VynFi journal entries.

Workflow: load the journal entry data, check the first digit pattern per
general ledger account on the train split, then apply the flagged accounts
to the test split and measure precision, recall, and F1.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from finlint.anomaly.dataset import LEAKAGE_COLUMNS, TARGET_COLUMN, load_train_test

MIN_AMOUNT = 0.01
MAD_THRESHOLD = 0.015
MIN_ROWS = 500

EXPECTED_DIGITS = np.arange(1, 10)
EXPECTED_SHARES = np.log10(1 + 1 / EXPECTED_DIGITS)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _out_dir() -> Path:
    out_dir = _repo_root() / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_split_data():
    """Load train and test through the shared, frozen split, ready for Benford.

    is_anomaly is dropped here too, alongside the usual leakage columns,
    since Benford only ever looks at amounts and gl_account, never at it.
    """
    train_df, test_df = load_train_test()

    y_test = test_df[TARGET_COLUMN].astype(int)

    drop_columns = LEAKAGE_COLUMNS + ["is_anomaly"]
    train_df = train_df.drop(columns=drop_columns, errors="ignore")
    test_df = test_df.drop(columns=drop_columns, errors="ignore")

    return train_df, test_df, y_test


def line_amounts(df: pd.DataFrame) -> pd.Series:
    """Debit and credit are separate columns, so combine them into one positive amount."""
    debit = df["debit_amount"].fillna(0)
    credit = df["credit_amount"].fillna(0)
    return (debit + credit).abs()


def first_digits(amount_series: pd.Series) -> pd.Series:
    """Benford only needs the first non-zero digit from each usable amount."""
    usable = amount_series[amount_series >= MIN_AMOUNT]
    scaled = usable / np.power(10.0, np.floor(np.log10(usable)))
    return scaled.astype(int).clip(1, 9)


def digit_shares(digit_series: pd.Series) -> np.ndarray:
    """Convert digit counts into proportions so they can be compared with Benford."""
    counts = digit_series.value_counts().reindex(EXPECTED_DIGITS, fill_value=0).to_numpy(dtype=float)
    total = counts.sum()
    if total == 0:
        return np.zeros(9)
    return counts / total


def mad_score(observed: np.ndarray) -> float:
    """Mean absolute deviation: one simple score for the average gap from Benford."""
    return float(np.mean(np.abs(observed - EXPECTED_SHARES)))


def digit_table(test_df: pd.DataFrame) -> pd.DataFrame:
    """Show which first digits differ most from the expected Benford pattern."""
    observed = digit_shares(first_digits(line_amounts(test_df)))
    return pd.DataFrame(
        {
            "digit": EXPECTED_DIGITS,
            "expected": EXPECTED_SHARES,
            "observed": observed,
            "difference": observed - EXPECTED_SHARES,
        }
    )


def score_accounts_by_mad(train_df: pd.DataFrame) -> pd.DataFrame:
    """Score every gl_account's digit pattern using training data only."""
    train_digits = first_digits(line_amounts(train_df))
    train_benford_data = pd.DataFrame(
        {
            "gl_account": train_df.loc[train_digits.index, "gl_account"].to_numpy(),
            "digit": train_digits.to_numpy(),
        }
    )

    rows = []
    for gl_account, chunk in train_benford_data.groupby("gl_account"):
        observed = digit_shares(chunk["digit"])
        mad_value = mad_score(observed)
        rows.append(
            {
                "gl_account": gl_account,
                "rows": len(chunk),
                "mad": mad_value,
                "testable": len(chunk) >= MIN_ROWS,
                "flagged": len(chunk) >= MIN_ROWS and mad_value > MAD_THRESHOLD,
            }
        )

    return pd.DataFrame(rows).sort_values("mad", ascending=False).reset_index(drop=True)


def run_benford() -> dict:
    """Run the full Benford check end to end and save its result tables."""
    train_df, test_df, y_test = load_split_data()

    group_scores = score_accounts_by_mad(train_df)
    failing_accounts = set(group_scores.loc[group_scores["flagged"], "gl_account"])
    test_pred = test_df["gl_account"].isin(failing_accounts).astype(int)

    # Report precision, recall and F1 because fraud data is imbalanced and accuracy can mislead.
    precision = precision_score(y_test, test_pred, zero_division=0)
    recall = recall_score(y_test, test_pred, zero_division=0)
    f1 = f1_score(y_test, test_pred, zero_division=0)

    out_dir = _out_dir()
    digit_table(test_df).to_csv(out_dir / "benford_digit_table.csv", index=False)
    group_scores.to_csv(out_dir / "benford_groups.csv", index=False)

    summary = {
        "method": "Benford (MAD by gl_account)",
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "n_flagged": int(test_pred.sum()),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "benford_summary.csv", index=False)
    return summary


if __name__ == "__main__":
    result = run_benford()
    print("Flagged accounts result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
