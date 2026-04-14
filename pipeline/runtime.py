from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
            self._stanza_coref_pipeline = self._stanza_factory(
                "pl",
                processors="tokenize,coref",
                coref_model_path=self.config.models.stanza_coref_model_path,
                download_method=DownloadMethod.REUSE_RESOURCES,
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
