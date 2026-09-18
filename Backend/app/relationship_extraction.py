"""Conservative fragment-scoped narrative relationship extraction."""

from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.ingestion import NormalizedDocument, NormalizedFragment
from app.schemas import Entity, Provenance, Relationship


RELATION_LABELS = (
    "CONTACTED",
    "MET",
    "VISITED",
    "LOCATED_AT",
    "WORKS_FOR",
    "USES_PHONE",
    "OWNS_VEHICLE",
    "TRANSFERRED_TO",
)
CLASSIFIER_LABELS = RELATION_LABELS + ("NO_RELATION",)
RELATION_SIGNATURES = {
    "CONTACTED": ("PERSON", "PERSON"),
    "MET": ("PERSON", "PERSON"),
    "VISITED": ("PERSON", "LOCATION"),
    "LOCATED_AT": ("PERSON", "LOCATION"),
    "WORKS_FOR": ("PERSON", "ORGANIZATION"),
    "USES_PHONE": ("PERSON", "PHONE_NUMBER"),
    "OWNS_VEHICLE": ("PERSON", "VEHICLE"),
    "TRANSFERRED_TO": ("PERSON", "ACCOUNT_NUMBER"),
}
SUPPORTED_SIGNATURES = frozenset(RELATION_SIGNATURES.values())
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = (
    _REPOSITORY_ROOT
    / ".relation-test"
    / "experiments"
    / "deberta-v3-small-revised"
    / "model"
)
DEFAULT_MODEL_NAME = "microsoft/deberta-v3-small"
DEFAULT_MODEL_VERSION = "deberta-v3-small-revised"
DEFAULT_THRESHOLD = 0.5
_SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")
_NEGATION_RE = re.compile(
    r"\b(?:(?:did|does|do)\s+not|never|no|without)\b", re.IGNORECASE
)


class RelationExtractionError(ValueError):
    """A relation candidate or classifier result cannot be handled safely."""


class RelationDecision(BaseModel):
    """Auditable intermediate decision for one ordered entity pair."""

    subject_entity: Entity
    object_entity: Entity
    predicted_relation: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    accepted: bool
    rejection_reason: str | None = None
    source_fragment_index: int = Field(ge=0)
    source_text: str
    subject_start: int = Field(ge=0)
    subject_end: int = Field(ge=1)
    object_start: int = Field(ge=0)
    object_end: int = Field(ge=1)
    source_location: dict[str, Any] = Field(default_factory=dict)
    model_name: str
    model_version: str


class RelationExtractionResult(BaseModel):
    """Final graph-ready edges plus every deterministic/model decision."""

    relationships: list[Relationship] = Field(default_factory=list)
    decisions: list[RelationDecision] = Field(default_factory=list)


class DeBERTaRelationClassifier:
    """Lazy local Hugging Face classifier, fixed to CPU/float32."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        model_version: str = DEFAULT_MODEL_VERSION,
        max_length: int = 192,
    ) -> None:
        configured_path = model_path or os.getenv(
            "CHANAKYA_RELATION_MODEL_DIR", str(DEFAULT_MODEL_PATH)
        )
        configured_path = Path(configured_path)
        if not configured_path.is_absolute():
            configured_path = _REPOSITORY_ROOT / configured_path
        self.model_path = configured_path.resolve()
        self.model_name = model_name
        self.model_version = model_version
        self.max_length = max_length
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"DeBERTa model directory does not exist: {self.model_path}")
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True
        )
        self._model = (
            AutoModelForSequenceClassification.from_pretrained(
                self.model_path, local_files_only=True
            )
            .float()
            .cpu()
            .eval()
        )
        self._torch = torch

    def predict(self, text: str) -> dict[str, Any]:
        self._load()
        encoded = self._tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits.float()
            probabilities = self._torch.softmax(logits, dim=-1)[0]
        prediction_id = int(probabilities.argmax().item())
        label = self._model.config.id2label[prediction_id]
        return {"label": label, "confidence": float(probabilities[prediction_id].item())}


class NarrativeRelationshipExtractor:
    """Generate, classify, and validate conservative same-sentence pairs."""

    def __init__(
        self,
        *,
        classifier: Any | None = None,
        model_path: str | Path | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ValueError("threshold must be a number between 0 and 1")
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be a finite number between 0 and 1")
        self.threshold = float(threshold)
        self._classifier = classifier or DeBERTaRelationClassifier(model_path)

    @property
    def model_name(self) -> str:
        return str(getattr(self._classifier, "model_name", DEFAULT_MODEL_NAME))

    @property
    def model_version(self) -> str:
        return str(getattr(self._classifier, "model_version", DEFAULT_MODEL_VERSION))

    def extract(
        self, document: NormalizedDocument, entities: Sequence[Entity]
    ) -> list[Relationship]:
        return self.extract_with_decisions(document, entities).relationships

    def extract_with_decisions(
        self, document: NormalizedDocument, entities: Sequence[Entity]
    ) -> RelationExtractionResult:
        grouped: dict[int, list[Entity]] = defaultdict(list)
        for entity in entities:
            fragment_index, _, _ = _entity_position(entity, document)
            grouped[fragment_index].append(entity)

        decisions: list[RelationDecision] = []
        relationships: list[Relationship] = []
        symmetric_edges: set[frozenset[str]] = set()

        for fragment_index in sorted(grouped):
            fragment = document.fragments[fragment_index]
            fragment_entities = sorted(
                grouped[fragment_index], key=lambda entity: _offsets(entity)
            )
            for subject in fragment_entities:
                for obj in fragment_entities:
                    if subject.id == obj.id or _offsets(subject) == _offsets(obj):
                        continue
                    subject_start, subject_end = _offsets(subject)
                    object_start, object_end = _offsets(obj)
                    if not _same_sentence(
                        fragment.content,
                        subject_start,
                        subject_end,
                        object_start,
                        object_end,
                    ):
                        continue
                    signature = (_entity_type(subject), _entity_type(obj))
                    if signature not in SUPPORTED_SIGNATURES:
                        decisions.append(
                            self._decision(
                                subject,
                                obj,
                                fragment,
                                fragment_index,
                                accepted=False,
                                rejection_reason="unsupported_entity_signature",
                            )
                        )
                        continue

                    model_input = _model_input(fragment.content, subject, obj)
                    label, confidence = _validate_prediction(
                        self._classifier.predict(model_input)
                    )
                    rejection_reason = _rejection_reason(
                        label=label,
                        confidence=confidence,
                        threshold=self.threshold,
                        signature=signature,
                        text=fragment.content,
                        subject_offsets=(subject_start, subject_end),
                        object_offsets=(object_start, object_end),
                    )
                    if rejection_reason is None and label == "MET":
                        symmetric_key = frozenset((subject.id, obj.id))
                        if symmetric_key in symmetric_edges:
                            rejection_reason = "duplicate_symmetric_relation"
                        else:
                            symmetric_edges.add(symmetric_key)

                    accepted = rejection_reason is None
                    decision = self._decision(
                        subject,
                        obj,
                        fragment,
                        fragment_index,
                        predicted_relation=label,
                        confidence=confidence,
                        accepted=accepted,
                        rejection_reason=rejection_reason,
                    )
                    decisions.append(decision)
                    if accepted:
                        relationships.append(
                            _relationship(
                                document,
                                decision,
                                len(relationships) + 1,
                            )
                        )

        return RelationExtractionResult(
            relationships=relationships,
            decisions=decisions,
        )

    def _decision(
        self,
        subject: Entity,
        obj: Entity,
        fragment: NormalizedFragment,
        fragment_index: int,
        *,
        predicted_relation: str | None = None,
        confidence: float | None = None,
        accepted: bool,
        rejection_reason: str | None,
    ) -> RelationDecision:
        subject_start, subject_end = _offsets(subject)
        object_start, object_end = _offsets(obj)
        return RelationDecision(
            subject_entity=subject,
            object_entity=obj,
            predicted_relation=predicted_relation,
            confidence=confidence,
            accepted=accepted,
            rejection_reason=rejection_reason,
            source_fragment_index=fragment_index,
            source_text=fragment.content,
            subject_start=subject_start,
            subject_end=subject_end,
            object_start=object_start,
            object_end=object_end,
            source_location=fragment.location.model_dump(exclude_none=True),
            model_name=self.model_name,
            model_version=self.model_version,
        )


def _entity_type(entity: Entity) -> str:
    return entity.type.strip().upper().replace("-", "_").replace(" ", "_")


def _offsets(entity: Entity) -> tuple[int, int]:
    start, end = entity.attributes.get("start"), entity.attributes.get("end")
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise RelationExtractionError(f"entity {entity.id}: invalid start/end offsets")
    return start, end


def _entity_position(
    entity: Entity, document: NormalizedDocument
) -> tuple[int, int, int]:
    fragment_index = entity.attributes.get("fragment_index")
    if type(fragment_index) is not int or not 0 <= fragment_index < len(document.fragments):
        raise RelationExtractionError(f"entity {entity.id}: invalid fragment_index")
    start, end = _offsets(entity)
    fragment = document.fragments[fragment_index]
    if end > len(fragment.content) or fragment.content[start:end] != entity.label:
        raise RelationExtractionError(
            f"entity {entity.id}: label does not match its fragment offsets"
        )
    return fragment_index, start, end


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans = [(match.start(), match.end()) for match in _SENTENCE_RE.finditer(text)]
    return spans or [(0, len(text))]


def _same_sentence(
    text: str,
    subject_start: int,
    subject_end: int,
    object_start: int,
    object_end: int,
) -> bool:
    return (
        _shared_sentence_span(
            text, subject_start, subject_end, object_start, object_end
        )
        is not None
    )


def _shared_sentence_span(
    text: str,
    subject_start: int,
    subject_end: int,
    object_start: int,
    object_end: int,
) -> tuple[int, int] | None:
    for start, end in _sentence_spans(text):
        if start <= subject_start < subject_end <= end and start <= object_start < object_end <= end:
            return start, end
    return None


def _model_input(text: str, subject: Entity, obj: Entity) -> str:
    subject_start, subject_end = _offsets(subject)
    object_start, object_end = _offsets(obj)
    if max(subject_start, object_start) < min(subject_end, object_end):
        raise RelationExtractionError("candidate entity mentions overlap")
    sentence_span = _shared_sentence_span(
        text, subject_start, subject_end, object_start, object_end
    )
    if sentence_span is None:
        raise RelationExtractionError("candidate entity mentions are not in the same sentence")
    sentence_start, sentence_end = sentence_span
    marked = text[sentence_start:sentence_end]
    mentions = (
        (subject_start - sentence_start, subject_end - sentence_start, "HEAD"),
        (object_start - sentence_start, object_end - sentence_start, "TAIL"),
    )
    for start, end, role in sorted(mentions, reverse=True):
        marked = f"{marked[:start]}<{role}>{marked[start:end]}</{role}>{marked[end:]}"
    return (
        f"SUBJECT [{_entity_type(subject)}]: {subject.label}\n"
        f"OBJECT [{_entity_type(obj)}]: {obj.label}\n"
        f"CONTEXT: {marked}"
    )


def _validate_prediction(result: Any) -> tuple[str, float]:
    if not isinstance(result, Mapping):
        raise RelationExtractionError("classifier result must be a mapping")
    label, confidence = result.get("label"), result.get("confidence")
    if label not in CLASSIFIER_LABELS:
        raise RelationExtractionError(f"classifier returned unsupported label: {label!r}")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise RelationExtractionError("classifier confidence must be between 0 and 1")
    return str(label), float(confidence)


def _rejection_reason(
    *,
    label: str,
    confidence: float,
    threshold: float,
    signature: tuple[str, str],
    text: str,
    subject_offsets: tuple[int, int],
    object_offsets: tuple[int, int],
) -> str | None:
    if label == "NO_RELATION":
        return "no_relation"
    if RELATION_SIGNATURES[label] != signature:
        return "predicted_relation_signature_mismatch"
    if confidence < threshold:
        return "below_confidence_threshold"
    sentence_span = _shared_sentence_span(
        text,
        subject_offsets[0],
        subject_offsets[1],
        object_offsets[0],
        object_offsets[1],
    )
    if sentence_span is not None and _NEGATION_RE.search(
        text[sentence_span[0] : sentence_span[1]]
    ):
        return "explicit_negation"
    return None


def _relationship(
    document: NormalizedDocument,
    decision: RelationDecision,
    sequence: int,
) -> Relationship:
    fragment = document.fragments[decision.source_fragment_index]
    location = fragment.location.model_dump(exclude_none=True)
    return Relationship(
        id=f"{document.document_id}:relationship:{sequence}",
        source_entity_id=decision.subject_entity.id,
        target_entity_id=decision.object_entity.id,
        type=decision.predicted_relation,
        confidence=decision.confidence,
        provenance=[
            Provenance(
                document_id=document.document_id,
                page_number=fragment.location.page_number,
                source_location=json.dumps(location, ensure_ascii=False) if location else None,
                evidence_text=decision.source_text,
                confidence=fragment.confidence,
            )
        ],
        attributes={
            "fragment_index": decision.source_fragment_index,
            "subject_start": decision.subject_start,
            "subject_end": decision.subject_end,
            "object_start": decision.object_start,
            "object_end": decision.object_end,
            "source_location": decision.source_location,
            "model_name": decision.model_name,
            "model_version": decision.model_version,
            "symmetric": decision.predicted_relation == "MET",
        },
    )
