import json
from typing import Any

import pytest

from app.entity_extraction import EntityExtractionError, GLiNEREntityExtractor
from app.ingestion import InputFormat, NormalizedDocument, NormalizedFragment, SourceLocation


class FakeGLiNER:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[str, list[str], float]] = []

    def predict_entities(
        self, text: str, labels: list[str], threshold: float
    ) -> list[dict[str, Any]]:
        self.calls.append((text, labels, threshold))
        return next(self.results)


def _document(*fragments: NormalizedFragment) -> NormalizedDocument:
    return NormalizedDocument(document_id="fir-001", format=InputFormat.TXT, fragments=list(fragments))


def _fragment(text: str, **location: Any) -> NormalizedFragment:
    return NormalizedFragment(
        content=text,
        original_value=text,
        location=SourceLocation(**location),
    )


def test_multiple_entities_map_values_offsets_and_fragment_evidence() -> None:
    fragment = NormalizedFragment(
        content="Alice called Bob",
        original_value="Alice called Bob",
        location=SourceLocation(page_number=2, line_number=7, source_path="report.pdf"),
        confidence=0.91,
    )
    fake = FakeGLiNER(
        [[
            {"text": "Alice", "label": "person", "score": 0.98, "start": 0, "end": 5},
            {"text": "Bob", "label": "person", "score": 0.87, "start": 13, "end": 16},
        ]]
    )

    entities = GLiNEREntityExtractor(model=fake, labels=["person"], threshold=0.4).extract(
        _document(fragment)
    )

    assert [(entity.id, entity.label, entity.type, entity.confidence) for entity in entities] == [
        ("fir-001:entity:1", "Alice", "person", 0.98),
        ("fir-001:entity:2", "Bob", "person", 0.87),
    ]
    assert [(entity.attributes["start"], entity.attributes["end"]) for entity in entities] == [
        (0, 5),
        (13, 16),
    ]
    assert all(entity.attributes["fragment_index"] == 0 for entity in entities)
    assert all(entity.attributes["original_value"] == fragment.original_value for entity in entities)
    assert all(entity.provenance[0].document_id == "fir-001" for entity in entities)
    assert all(entity.provenance[0].page_number == 2 for entity in entities)
    assert all(entity.provenance[0].evidence_text == fragment.content for entity in entities)
    assert all(entity.provenance[0].confidence == 0.91 for entity in entities)
    assert all(
        json.loads(entity.provenance[0].source_location) == fragment.location.model_dump(exclude_none=True)
        for entity in entities
    )
    assert fake.calls == [(fragment.content, ["person"], 0.4)]


def test_empty_fragments_do_not_load_or_call_model() -> None:
    extractor = GLiNEREntityExtractor(model=FakeGLiNER([]))
    assert extractor.extract(_document(_fragment(""), _fragment("  "))) == []
    assert extractor._model.calls == []


def test_multiple_fragments_remain_provenance_separated() -> None:
    fake = FakeGLiNER(
        [
            [{"text": "Alice", "label": "person", "score": 0.9, "start": 0, "end": 5}],
            [{"text": "Bob", "label": "person", "score": 0.8, "start": 0, "end": 3}],
        ]
    )
    document = _document(
        _fragment("Alice", line_number=1, source_path="report.txt", character_start=0, character_end=5),
        _fragment("Bob", line_number=2, source_path="report.txt", character_start=6, character_end=9),
    )

    entities = GLiNEREntityExtractor(model=fake).extract(document)

    assert [entity.attributes["fragment_index"] for entity in entities] == [0, 1]
    assert [entity.attributes["start"] for entity in entities] == [0, 0]
    assert [entity.provenance[0].evidence_text for entity in entities] == ["Alice", "Bob"]
    assert [json.loads(entity.provenance[0].source_location)["line_number"] for entity in entities] == [1, 2]
    assert [entity.attributes["source_location"]["character_start"] for entity in entities] == [0, 6]
    assert [call[0] for call in fake.calls] == ["Alice", "Bob"]


@pytest.mark.parametrize(
    "result, message",
    [
        ({"text": "Alice", "label": "person", "score": 0.9}, "missing GLiNER fields"),
        ({"text": "Alice", "label": "person", "score": 1.1, "start": 0, "end": 5}, "score"),
        ({"text": "Alice", "label": "person", "score": 0.9, "start": 0, "end": 9}, "offsets"),
        ({"text": "Bob", "label": "person", "score": 0.9, "start": 0, "end": 3}, "does not match"),
        ("invalid", "must be a mapping"),
    ],
)
def test_invalid_model_results_raise_clear_errors(result: Any, message: str) -> None:
    fake = FakeGLiNER([[result]])
    with pytest.raises(EntityExtractionError, match=message):
        GLiNEREntityExtractor(model=fake).extract(_document(_fragment("Alice")))


def test_model_is_loaded_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import ModuleType
    import sys

    fake_module = ModuleType("gliner")
    fake = FakeGLiNER([[]])
    loaded: list[str] = []

    class FakeFactory:
        @staticmethod
        def from_pretrained(model_name: str) -> FakeGLiNER:
            loaded.append(model_name)
            return fake

    fake_module.GLiNER = FakeFactory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gliner", fake_module)
    extractor = GLiNEREntityExtractor(model_name="test-model")
    assert loaded == []
    extractor.extract(_document(_fragment("Alice")))
    assert loaded == ["test-model"]
