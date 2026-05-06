from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import spacy
import stanza
from sentence_transformers import SentenceTransformer
from stanza import DownloadMethod

from pipeline.config import PipelineConfig

type SpacyLoader = Callable[[str], Any]
type StanzaFactory = Callable[..., Any]
type SentenceTransformerLoader = Callable[[str], Any]


class PipelineRuntime:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        spacy_loader: SpacyLoader | None = None,
        stanza_factory: StanzaFactory | None = None,
        sentence_transformer_loader: SentenceTransformerLoader | None = None,
    ) -> None:
        self.config = config
        self._spacy_loader = spacy_loader or spacy.load
        self._stanza_factory = stanza_factory or stanza.Pipeline
        self._sentence_transformer_loader = sentence_transformer_loader or SentenceTransformer
        self._spacy_model: Any | None = None
        self._stanza_coref_pipeline: Any | None = None
        self._stanza_syntax_pipeline: Any | None = None
        self._sentence_transformer_model: Any | None = None
        self._embedding_cache: dict[str, np.ndarray] = {}

    @property
    def spacy_loaded(self) -> bool:
        return self._spacy_model is not None

    @property
    def stanza_coref_loaded(self) -> bool:
        return self._stanza_coref_pipeline is not None

    @property
    def stanza_syntax_loaded(self) -> bool:
        return self._stanza_syntax_pipeline is not None

    @property
    def sentence_transformer_loaded(self) -> bool:
        return self._sentence_transformer_model is not None

    def get_spacy_model(self) -> Any:
        if self._spacy_model is None:
            self._spacy_model = self._spacy_loader(self.config.models.spacy_model)
        return self._spacy_model

    def get_stanza_coref_pipeline(self) -> Any:
        if self._stanza_coref_pipeline is None:
            coref_model_path = Path(self.config.models.stanza_coref_model_path)
            if not coref_model_path.exists():
                msg = (
                    f"Missing Stanza coref model at {coref_model_path}. "
                    "Run `uv run python scripts/setup_models.py` first."
                )
                raise FileNotFoundError(msg)
            self._stanza_coref_pipeline = self._stanza_factory(
                "pl",
                processors="tokenize,coref",
                coref_model_path=self.config.models.stanza_coref_model_path,
                # Coref assets must be provisioned up front via scripts/setup_models.py.
                download_method=DownloadMethod.NONE,
            )
        return self._stanza_coref_pipeline

    def reset_stanza_coref_pipeline(self) -> None:
        self._stanza_coref_pipeline = None

    def get_stanza_syntax_pipeline(self) -> Any:
        if self._stanza_syntax_pipeline is None:
            self._stanza_syntax_pipeline = self._stanza_factory(
                "pl",
                processors="tokenize,mwt,pos,lemma,depparse",
                download_method=DownloadMethod.REUSE_RESOURCES,
            )
        return self._stanza_syntax_pipeline

    def get_sentence_transformer_model(self) -> Any:
        if self._sentence_transformer_model is None:
            self._sentence_transformer_model = self._sentence_transformer_loader(
                self.config.models.sentence_transformer_model
            )
        return self._sentence_transformer_model

    def encode_text(self, text: str) -> np.ndarray:
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        model = self.get_sentence_transformer_model()
        try:
            encoded = model.encode(text, normalize_embeddings=True)
        except (TypeError, AttributeError):
            encoded = model.encode(text)
        vector = np.asarray(encoded, dtype=float)
        if vector.ndim != 1:
            vector = vector.reshape(-1)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        self._embedding_cache[text] = vector
        return vector
