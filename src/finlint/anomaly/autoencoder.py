"""PyTorch autoencoder on the VynFi journal entries.

Trained only on the non-fraud rows of train, so it learns what a normal
transaction looks like. A row that reconstructs badly on test, measured as
the average absolute difference between input and output, is flagged as
unusual. The cutoff itself comes from the 95th percentile of the model's
own reconstruction error on the training data it learned from, not from a
number picked by hand.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import classification_report
from sklearn.preprocessing import MinMaxScaler
from torch.utils.data import DataLoader

from finlint.anomaly.dataset import build_features, load_train_test

EPOCHS = 25
BATCH_SIZE = 1000
LATENT_DIM = 10
HIDDEN_DIM = 16
LEARNING_RATE = 0.001
RANDOM_SEED = 42


class AutoEncoder(nn.Module):
    """Squeeze input_dim down to latent_dim, then rebuild it back up."""

    def __init__(self, input_dim: int, latent_dim: int, hidden_dim: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim),
            # Sigmoid bounds the output to 0 to 1, matching the MinMaxScaler
            # range the inputs are scaled into.
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


def _out_dir() -> Path:
    out_dir = Path(__file__).resolve().parents[3] / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _reconstruction_error(model: AutoEncoder, scaled_data: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        tensor = torch.tensor(scaled_data.astype(np.float32), dtype=torch.float32)
        reconstruction = model(tensor).numpy()
    return np.mean(np.abs(reconstruction - scaled_data), axis=1)


def train_autoencoder(training_data: np.ndarray, input_dim: int) -> AutoEncoder:
    torch.manual_seed(RANDOM_SEED)
    model = AutoEncoder(input_dim=input_dim, latent_dim=LATENT_DIM, hidden_dim=HIDDEN_DIM)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

    train_loader = DataLoader(
        torch.tensor(training_data.astype(np.float32), dtype=torch.float32),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    model.train()
    for _ in range(EPOCHS):
        for batch in train_loader:
            optimizer.zero_grad()
            reconstruction = model(batch)
            loss = criterion(reconstruction, batch)
            loss.backward()
            optimizer.step()

    return model


def run_autoencoder() -> dict:
    """Train the autoencoder on non-fraud rows only, evaluate on all of test."""
    train_df, test_df = load_train_test()
    train_normal = train_df[train_df["is_fraud"] == 0]

    X_train, X_test, _, y_test = build_features(train_normal, test_df)

    scaler = MinMaxScaler().fit(X_train)
    training_data = scaler.transform(X_train)
    test_data = scaler.transform(X_test)

    model = train_autoencoder(training_data, input_dim=X_train.shape[1])

    test_error = _reconstruction_error(model, test_data)
    train_error = _reconstruction_error(model, training_data)

    threshold = np.percentile(train_error, 95)
    pred = pd.cut(test_error, bins=[-1, threshold, float("inf")], labels=[0, 1]).astype(int)

    report = classification_report(y_test, pred, output_dict=True, zero_division=0)
    fraud_row = report["True"]

    out_dir = _out_dir()
    torch.save(model.state_dict(), out_dir / "autoencoder_state.pt")

    summary = {
        "method": "Autoencoder",
        "precision": round(fraud_row["precision"], 4),
        "recall": round(fraud_row["recall"], 4),
        "f1": round(fraud_row["f1-score"], 4),
        "n_flagged": int(pred.sum()),
        "threshold": round(float(threshold), 6),
    }
    pd.DataFrame([summary]).to_csv(out_dir / "autoencoder_summary.csv", index=False)

    return {"summary": summary}


if __name__ == "__main__":
    outputs = run_autoencoder()
    for key, value in outputs["summary"].items():
        print(f"{key}: {value}")
