"""Supervised fraud models on the VynFi journal entries.

Trains a logistic regression (linear baseline) and a histogram gradient
boosting model (non-linear) on the same engineered features, using the real
is_fraud label. Unlike the other three methods, these see the label during
training, so they are expected to outperform them, that comparison is the
point.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from finlint.anomaly.dataset import LEAKAGE_COLUMNS, TARGET_COLUMN, load_train_test

NUMERIC_FEATURES = [
    "amount",
    "log10_amount",
    "first_digit",
    "posting_lag_days",
    "posting_dayofweek",
    "exchange_rate",
    "line_number",
    "fiscal_period",
]

BOOLEAN_FEATURES = [
    "is_debit",
    "is_round_100",
    "is_round_1000",
    "is_weekend",
    "is_manual",
    "is_post_close",
]

CATEGORICAL_FEATURES = [
    "document_type",
    "currency",
    "business_process",
    "business_unit",
    "account_class",
    "account_sub_class",
    "financial_statement_category",
    "source_system",
    "company_code",
]

ACCOUNT_FEATURE = "gl_account"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _out_dir() -> Path:
    out_dir = _repo_root() / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_split_data():
    """Load train and test through the shared, frozen split.

    fraud_type is kept aside for test rows only, so the final report can
    show recall broken down by fraud type, without it ever reaching a model
    as a feature.
    """
    train_df, test_df = load_train_test()
    eval_fraud_type = test_df["fraud_type"].copy()

    y_train = train_df[TARGET_COLUMN].astype(int)
    y_test = test_df[TARGET_COLUMN].astype(int)

    drop_columns = LEAKAGE_COLUMNS + ["is_anomaly"]
    train_df = train_df.drop(columns=drop_columns, errors="ignore")
    test_df = test_df.drop(columns=drop_columns, errors="ignore")

    return train_df, test_df, y_train, y_test, eval_fraud_type


def engineer_supervised_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build a richer feature table with a possible accounting meaning.

    Distinct from dataset.build_features, which builds the smaller feature
    set the unsupervised methods use.
    """
    out = pd.DataFrame(index=df.index)

    debit = df["debit_amount"].fillna(0)
    credit = df["credit_amount"].fillna(0)
    amount = (debit + credit).abs()

    # The log amount reduces the effect of a few extremely large transactions.
    out["amount"] = amount
    out["log10_amount"] = np.log10(amount.clip(lower=0.01))

    scaled = amount.clip(lower=0.01) / np.power(10.0, np.floor(np.log10(amount.clip(lower=0.01))))
    out["first_digit"] = scaled.astype(int).clip(1, 9)

    # Round and debit indicators may help identify unusual manual-looking entries.
    out["is_debit"] = (debit > 0).astype(int)
    out["is_round_100"] = ((amount > 0) & (amount % 100 == 0)).astype(int)
    out["is_round_1000"] = ((amount > 0) & (amount % 1000 == 0)).astype(int)

    # Date features can show delayed postings or entries made during weekends.
    lag = (df["posting_date"] - df["document_date"]).dt.days
    out["posting_lag_days"] = lag.fillna(0)
    out["posting_dayofweek"] = df["posting_date"].dt.dayofweek.fillna(0)
    out["is_weekend"] = (df["posting_date"].dt.dayofweek >= 5).astype(int)

    out["exchange_rate"] = df["exchange_rate"].fillna(1.0)
    out["line_number"] = df["line_number"].fillna(0)
    out["fiscal_period"] = df["fiscal_period"].fillna(0)
    out["is_manual"] = df["is_manual"].astype(int)
    out["is_post_close"] = df["is_post_close"].astype(int)

    # Missing text values get their own label instead of being silently dropped.
    for column in CATEGORICAL_FEATURES:
        out[column] = df[column].astype("string").fillna("missing")

    out[ACCOUNT_FEATURE] = df[ACCOUNT_FEATURE].fillna(-1).astype("int64")
    return out


def _build_logistic_model() -> Pipeline:
    """Logistic regression needs scaled numbers and one-hot encoded categories."""
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                NUMERIC_FEATURES + BOOLEAN_FEATURES,
            ),
            (
                "cat",
                OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50, sparse_output=True),
                CATEGORICAL_FEATURES + [ACCOUNT_FEATURE],
            ),
        ],
        remainder="drop",
    )
    return Pipeline(
        steps=[
            ("prep", preprocessor),
            (
                "model",
                LogisticRegression(
                    max_iter=1000,
                    # Fraud rows are rare, so balanced weights give them more importance.
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def _build_gradient_model() -> Pipeline:
    """The tree model does not need scaling, but its categories still need numeric codes."""
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                SimpleImputer(strategy="median"),
                NUMERIC_FEATURES + BOOLEAN_FEATURES + [ACCOUNT_FEATURE],
            ),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )
    n_numeric = len(NUMERIC_FEATURES) + len(BOOLEAN_FEATURES) + 1
    # These positions tell the gradient model which processed columns are categories.
    categorical_positions = list(range(n_numeric, n_numeric + len(CATEGORICAL_FEATURES)))
    return Pipeline(
        steps=[
            ("prep", preprocessor),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_iter=300,
                    learning_rate=0.1,
                    class_weight="balanced",
                    categorical_features=categorical_positions,
                    random_state=42,
                ),
            ),
        ]
    )


def score_method(method_name, y_true, y_pred, y_score) -> dict:
    """Keep all model metrics in the same shape so the comparison is easy."""
    return {
        "method": method_name,
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "average_precision": round(average_precision_score(y_true, y_score), 4),
        "roc_auc": round(roc_auc_score(y_true, y_score), 4),
        "n_flagged": int(np.sum(y_pred)),
    }


def recall_by_fraud_type(y_true, y_pred, fraud_type) -> pd.DataFrame:
    """Recall broken down by fraud type shows which kinds of fraud each model misses."""
    result = pd.DataFrame(
        {
            "is_fraud": pd.Series(y_true).astype(bool),
            "caught": pd.Series(y_pred).astype(bool),
            "fraud_type": pd.Series(fraud_type),
        }
    )
    fraud_only = result[result["is_fraud"]]
    summary = fraud_only.groupby("fraud_type", observed=True)["caught"].agg(["size", "sum", "mean"])
    summary.columns = ["fraud_rows", "caught", "recall"]
    return summary.sort_values("fraud_rows", ascending=False).reset_index()


def run_supervised() -> dict:
    """Train both supervised models end to end and save their result tables."""
    train_df, test_df, y_train, y_test, eval_fraud_type = load_split_data()

    X_train = engineer_supervised_features(train_df)
    X_test = engineer_supervised_features(test_df)

    logistic_model = _build_logistic_model()
    logistic_model.fit(X_train, y_train)
    logistic_pred = logistic_model.predict(X_test)
    logistic_score = logistic_model.predict_proba(X_test)[:, 1]

    gradient_model = _build_gradient_model()
    gradient_model.fit(X_train, y_train)
    gradient_pred = gradient_model.predict(X_test)
    gradient_score = gradient_model.predict_proba(X_test)[:, 1]

    results_table = pd.DataFrame(
        [
            score_method("Logistic regression", y_test, logistic_pred, logistic_score),
            score_method("Gradient boosting", y_test, gradient_pred, gradient_score),
        ]
    )

    logistic_by_type = recall_by_fraud_type(y_test, logistic_pred, eval_fraud_type)
    logistic_by_type.insert(0, "method", "Logistic regression")
    gradient_by_type = recall_by_fraud_type(y_test, gradient_pred, eval_fraud_type)
    gradient_by_type.insert(0, "method", "Gradient boosting")
    recall_table = pd.concat([logistic_by_type, gradient_by_type], ignore_index=True)

    out_dir = _out_dir()
    results_table.to_csv(out_dir / "supervised_results.csv", index=False)
    recall_table.to_csv(out_dir / "supervised_recall_by_fraud_type.csv", index=False)

    return {
        "results_table": results_table,
        "recall_by_fraud_type": recall_table,
    }


if __name__ == "__main__":
    outputs = run_supervised()
    print(outputs["results_table"])
    print()
    print(outputs["recall_by_fraud_type"])
