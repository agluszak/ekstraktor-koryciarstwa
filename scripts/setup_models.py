from __future__ import annotations

import hashlib
from pathlib import Path

import spacy
import spacy.cli
import stanza

SPACY_MODELS = ("pl_core_news_lg", "pl_core_news_md")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_spacy_model() -> None:
    for model_name in SPACY_MODELS:
        try:
            spacy.load(model_name)
        except OSError:
            spacy.cli.download(model_name)


def ensure_stanza_models() -> None:
    stanza.download("pl", processors="tokenize,mwt,pos,lemma,depparse", verbose=True)


def main() -> int:
    ensure_spacy_model()
    ensure_stanza_models()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
