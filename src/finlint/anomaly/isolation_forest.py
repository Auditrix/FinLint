"""Isolation Forest on the VynFi journal entries.

Isolation Forest never sees the is_fraud label during training, it only
learns to isolate points that look statistically rare in the engineered
feature space. contamination is set from the real training fraud rate, a
fair use of the label as a setting, not as something the model is trained
on directly.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pyod.models.iforest import IForest
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_curve

from finlint.anomaly.dataset import build_features, load_train_test


def _out_dir() -> Path:
    out_dir = Path(__file__).resolve().parents[3] / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def run_isolation_forest() -> dict:
    """Fit Isolation Forest on train, evaluate on test, save the PR curve."""
    train_df, test_df = load_train_test()
    X_train, X_test, y_train, y_test = build_features(train_df, test_df)

    model = IForest(n_estimators=100, contamination=y_train.mean(), random_state=42)
    model.fit(X_train)

    pred = model.predict(X_test)
    scores = model.decision_function(X_test)

    report = classification_report(y_test, pred, output_dict=True, zero_division=0)
    fraud_row = report["True"]

    precision, recall, _ = precision_recall_curve(y_test, scores)
    out_dir = _out_dir()
    plt.figure(facecolor="white")
    plt.plot(recall, precision, marker=".", color="#F97316", linewidth=2)
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Isolation Forest, precision vs recall at every threshold")
    plt.grid(alpha=0.3)
    plt.gca().set_facecolor("white")
    plt.savefig(out_dir / "isolation_forest_pr_curve.png", facecolor="white")
    plt.close()

    summary = {
        "method": "Isolation Forest",
        "precision": round(fraud_row["precision"], 4),
        "recall": round(fraud_row["recall"], 4),
        "f1": round(fraud_row["f1-score"], 4),
        "n_flagged": int(pred.sum()),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "isolation_forest_summary.csv", index=False)

    return {
        "summary": summary,
        "confusion_matrix": confusion_matrix(y_test, pred),
    }


if __name__ == "__main__":
    result = run_isolation_forest()
    print("Confusion matrix:")
    print(result["confusion_matrix"])
    print("Summary:")
    for key, value in result["summary"].items():
        print(f"  {key}: {value}")
