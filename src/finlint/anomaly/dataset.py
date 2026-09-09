from pathlib import Path

import pandas as pd

TARGET_COLUMN = "is_fraud"
LEAKAGE_COLUMNS = ["fraud_type", "anomaly_type"]

# Completely empty across every row, checked during data exploration. No signal, always dropped.
EMPTY_COLUMNS = [
    "auxiliary_account_number",
    "auxiliary_account_label",
    "lettrage",
    "lettrage_date",
    "tax_code",
]

SHARD_NAMES = [
    "train-00000-of-00003.parquet",
    "train-00001-of-00003.parquet",
    "train-00002-of-00003.parquet",
]

# Bucket edges for the days between posting_date and document_date. A 1 to 7 day
# gap is a strong fraud signal in this dataset (86 to 91 percent fraud in that
# band, versus about 4 percent at gap 0), found during exploration.
GAP_BINS = [-1, 0, 1, 3, 7, 30, 10000]
GAP_LABELS = ["0", "1", "2-3", "4-7", "8-30", "30+"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_dir() -> Path:
    return _repo_root() / "data" / "training" / "vynfi"


def _frozen_test_document_ids() -> set:
    """The test side of the grouped split, frozen once and committed to git.

    StratifiedGroupKFold with a fixed random_state still produced a
    different split across two machines on different scikit-learn
    versions, so the split itself is not recomputed here. It was run once
    and its result saved, so every model, on any machine, sees the exact
    same rows.
    """
    splits_path = _repo_root() / "splits" / "test_document_ids.csv"
    return set(pd.read_csv(splits_path)["document_id"])


def load_train_test():
    """Load the three VynFi shards and split using the frozen document_id list.

    Grouping by document_id, done once when the split was frozen, keeps
    every line of one journal entry on the same side, so a document can
    never leak across train and test.
    """
    data_dir = _data_dir()
    main_data = pd.concat(
        [pd.read_parquet(data_dir / name) for name in SHARD_NAMES],
        ignore_index=True,
    )
    main_data = main_data.drop(columns=EMPTY_COLUMNS, errors="ignore")

    gap_days = (main_data["posting_date"] - main_data["document_date"]).dt.days
    main_data["gap"] = pd.cut(gap_days, bins=GAP_BINS, labels=GAP_LABELS)

    test_ids = _frozen_test_document_ids()
    is_test = main_data["document_id"].isin(test_ids)

    train_df = main_data.loc[~is_test].reset_index(drop=True)
    test_df = main_data.loc[is_test].reset_index(drop=True)
    return train_df, test_df


def build_features(train_df, test_df):
    feature_columns = [
        "debit_amount", "credit_amount", "local_amount", "exchange_rate",
        "gl_account", "fiscal_year", "document_type", "is_post_close", "gap",
    ]

    X_train = train_df[feature_columns]
    X_test = test_df[feature_columns]

    X_train = pd.get_dummies(X_train, columns=["document_type", "gap"])
    X_test = pd.get_dummies(X_test, columns=["document_type", "gap"])
    X_test = X_test.reindex(columns=X_train.columns, fill_value=0)

    y_train = train_df[TARGET_COLUMN]
    y_test = test_df[TARGET_COLUMN]

    return X_train, X_test, y_train, y_test
