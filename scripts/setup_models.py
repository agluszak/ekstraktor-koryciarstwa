from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

import spacy.cli
import stanza
import torch

SPACY_MODEL = "pl_core_news_lg"
COREf_URL = "https://huggingface.co/stanfordnlp/stanza-pl/resolve/v1.12.0/models/coref/udcoref_xlm-roberta-lora.pt"
RAW_COREF_PATH = Path("models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.pt")
PATCHED_COREF_PATH = Path("models/stanza/pl/coref/udcoref_xlm-roberta-lora-v1.12.0.patched.pt")
PLATEAU_EPOCHS_DEFAULT = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_spacy_model() -> None:
    try:
        spacy.load(SPACY_MODEL)
    except OSError:
        spacy.cli.download(SPACY_MODEL)


def ensure_stanza_models() -> None:
    stanza.download("pl", processors="tokenize,mwt,pos,lemma,depparse", verbose=True)


def download_coref_model() -> None:
    RAW_COREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAW_COREF_PATH.exists():
        return
    with urllib.request.urlopen(COREf_URL) as response, RAW_COREF_PATH.open("wb") as output:
        shutil.copyfileobj(response, output)


def patch_coref_model() -> None:
    state = torch.load(RAW_COREF_PATH, map_location="cpu", weights_only=False)
    config = state["config"]
    if "plateau_epochs" not in config:
        config["plateau_epochs"] = PLATEAU_EPOCHS_DEFAULT
    torch.save(state, PATCHED_COREF_PATH)


def main() -> int:
    ensure_spacy_model()
    ensure_stanza_models()
    download_coref_model()
    patch_coref_model()
    print(
        {
            "raw_model": str(RAW_COREF_PATH),
            "raw_sha256": sha256_file(RAW_COREF_PATH),
            "patched_model": str(PATCHED_COREF_PATH),
            "patched_sha256": sha256_file(PATCHED_COREF_PATH),
            "plateau_epochs": PLATEAU_EPOCHS_DEFAULT,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
