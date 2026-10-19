# Standard Colab setup

Google Colab is a free hosted notebook service with GPU access (GPU means graphics processing unit, the chip that makes neural network training fast). Per the 3 September decision, Colab is used only 2 or 3 times in the whole project: autoencoder training in the ML week, and embedding generation in the RAG week. Everything else runs on laptops.

## Notebook discipline (agreed rules)

1. Real logic lives in `.py` files in the repo. Notebooks are thin drivers that import and call them.
2. Each person works in their OWN notebook. No shared notebook editing.
3. Clear all outputs before committing a notebook.
4. API keys go in Colab Secrets (the key icon in the left sidebar), never in cells.

## Before you start

For GPU training: menu Runtime, then Change runtime type, then pick T4 GPU.

The shared Drive folder `FinLint-data` must be reachable from your own Drive. If it was shared with you, open Google Drive in the browser, right click `FinLint-data`, and choose Organise then Add shortcut, placing the shortcut in My Drive. The paths below assume that shortcut exists.

## Cell 1: get the code

```python
!git clone https://github.com/auditrix/finlint.git
%cd finlint
!pip install -q -e .
```

If the repo is private, create a fine grained GitHub token, store it in Colab Secrets as `GITHUB_TOKEN`, and clone like this instead:

```python
from google.colab import userdata
token = userdata.get("GITHUB_TOKEN")
!git clone https://{token}@github.com/auditrix/finlint.git
%cd finlint
!pip install -q -e .
```

## Cell 2: get the data from the shared Drive folder

```python
from google.colab import drive
drive.mount("/content/drive")

import shutil, pathlib
src = pathlib.Path("/content/drive/MyDrive/FinLint-data/raw/vynfi")
dst = pathlib.Path("data/training/vynfi")
dst.mkdir(parents=True, exist_ok=True)
for f in src.glob("*.parquet"):
    shutil.copy(f, dst / f.name)
print(sorted(p.name for p in dst.iterdir()))
```

Copying out of Drive matters: reading parquet files directly from the mounted Drive path is slow and flaky during training.

## Cell 3: secrets, only if the notebook needs a key

Most ML week work needs no key at all. When one is needed:

```python
from google.colab import userdata
import os
os.environ["GROQ_API_KEY"] = userdata.get("GROQ_API_KEY")
```

## Saving results

Model weights (`*.pt` files) are gitignored. Save them to Drive so they survive the Colab session ending:

```python
shutil.copy("autoencoder.pt", "/content/drive/MyDrive/FinLint-data/generated/autoencoder.pt")
```
