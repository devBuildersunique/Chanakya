"""Fragment-scoped GLiNER entity extraction with source evidence intact."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.ingestion import InputFormat, NormalizedDocument, NormalizedFragment, SourceLocation
from app.schemas import Entity, Provenance

DEFAULT_MODEL = "gliner-community/gliner_small-v2.5"
DEFAULT_LABELS = (
    "person",
    "organization",
    "location",
    "vehicle",
    "phone_number",
    "email",
    "date",
    "time",
    "money",
    "account_number",
    "case_number",
)
DEFAULT_THRESHOLD = 0.5


class EntityExtractionError(ValueError):
    """A GLiNER result cannot be mapped safely to its source fragment."""


class GLiNEREntityExtractor:
    """Load GLiNER on first use and extract independently from each fragment."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        labels: Sequence[str] = DEFAULT_LABELS,
        threshold: float = DEFAULT_THRESHOLD,
        model: Any | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("labels must contain non-empty strings")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be a finite number between 0 and 1")
        self.model_name = model_name
        self.labels = tuple(labels)
        self.threshold = float(threshold)
        self._model = model

    def _get_model(self) -> Any:
        if self._model is None:
            from gliner import GLiNER

            self._model = GLiNER.from_pretrained(self.model_name)
        return self._model

    def extract(self, document: NormalizedDocument) -> list[Entity]:
        """Return document-local mentions; offsets are relative to each fragment."""

        entities: list[Entity] = []
        for fragment_index, fragment in enumerate(document.fragments):
            if not fragment.content.strip():
                continue
            results = self._get_model().predict_entities(
                fragment.content, list(self.labels), threshold=self.threshold
            )
            if not isinstance(results, (list, tuple)):
                raise EntityExtractionError(
                    f"fragment {fragment_index}: GLiNER results must be a list or tuple"
                )
            for result_index, result in enumerate(results):
                mention = _validate_result(result, fragment, fragment_index, result_index)
                location = fragment.location.model_dump(exclude_none=True)
                entities.append(
                    Entity(
                        id=f"{document.document_id}:entity:{len(entities) + 1}",
                        type=mention["label"],
                        label=mention["text"],
                        confidence=mention["score"],
                        provenance=[
                            Provenance(
                                document_id=document.document_id,
                                page_number=fragment.location.page_number,
                                source_location=json.dumps(location, ensure_ascii=False)
                                if location
                                else None,
                                evidence_text=fragment.content,
                                confidence=fragment.confidence,
                            )
                        ],
                        attributes={
                            "fragment_index": fragment_index,
                            "start": mention["start"],
                            "end": mention["end"],
                            "source_location": location,
                            "original_value": fragment.original_value,
                        },
                    )
                )
        return entities


def _validate_result(
    result: Any, fragment: NormalizedFragment, fragment_index: int, result_index: int
) -> dict[str, Any]:
    prefix = f"fragment {fragment_index}, result {result_index}"
    if not isinstance(result, Mapping):
        raise EntityExtractionError(f"{prefix}: GLiNER result must be a mapping")
    required = {"text", "label", "score", "start", "end"}
    missing = required - result.keys()
    if missing:
        raise EntityExtractionError(f"{prefix}: missing GLiNER fields: {', '.join(sorted(missing))}")
    text, label, score, start, end = (result[key] for key in ("text", "label", "score", "start", "end"))
    if not isinstance(text, str) or not text or not isinstance(label, str) or not label.strip():
        raise EntityExtractionError(f"{prefix}: text and label must be non-empty strings")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1:
        raise EntityExtractionError(f"{prefix}: score must be a finite number between 0 and 1")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(fragment.content):
        raise EntityExtractionError(f"{prefix}: invalid fragment-relative start/end offsets")
    if fragment.content[start:end] != text:
        raise EntityExtractionError(f"{prefix}: text does not match fragment at start/end offsets")
    return {"text": text, "label": label, "score": float(score), "start": start, "end": end}


def main() -> None:
    """Manual smoke path: python -m app.entity_extraction --text 'Alice met Bob.'"""

    parser = argparse.ArgumentParser(description="Run GLiNER on one manually supplied text fragment")
    parser.add_argument("--text", required=True)
    parser.add_argument("--document-id", default="manual")
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--labels", nargs="+", default=list(DEFAULT_LABELS))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()
    document = NormalizedDocument(
        document_id=args.document_id,
        format=InputFormat.TXT,
        fragments=[NormalizedFragment(content=args.text, original_value=args.text, location=SourceLocation())],
    )
    entities = GLiNEREntityExtractor(
        model_name=args.model_name, labels=args.labels, threshold=args.threshold
    ).extract(document)
    print(json.dumps([entity.model_dump() for entity in entities], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
