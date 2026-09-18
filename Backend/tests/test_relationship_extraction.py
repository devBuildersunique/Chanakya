import re
from typing import Any

from app.ingestion import InputFormat, NormalizedDocument, NormalizedFragment, SourceLocation
from app.relationship_extraction import DeBERTaRelationClassifier, NarrativeRelationshipExtractor
from app.schemas import Entity, Provenance


class FakeClassifier:
    model_name = "fake-deberta"
    model_version = "test"

    def __init__(self, predictions: dict[tuple[str, str], tuple[str, float]]) -> None:
        self.predictions = predictions
        self.calls: list[tuple[str, str]] = []
        self.inputs: list[str] = []

    def predict(self, text: str) -> dict[str, Any]:
        self.inputs.append(text)
        subject = re.search(r"^SUBJECT \[[^]]+\]: (.+)$", text, re.MULTILINE).group(1)
        obj = re.search(r"^OBJECT \[[^]]+\]: (.+)$", text, re.MULTILINE).group(1)
        self.calls.append((subject, obj))
        label, confidence = self.predictions.get((subject, obj), ("NO_RELATION", 0.99))
        return {"label": label, "confidence": confidence}


def _fixture(text: str, mentions: list[tuple[str, str]]) -> tuple[NormalizedDocument, list[Entity]]:
    fragment = NormalizedFragment(
        content=text,
        original_value=text,
        location=SourceLocation(page_number=2, line_number=7, source_path="report.txt"),
        confidence=0.91,
    )
    document = NormalizedDocument(
        document_id="fir-001", format=InputFormat.TXT, fragments=[fragment]
    )
    entities = []
    search_from = 0
    for index, (surface, entity_type) in enumerate(mentions, start=1):
        start = text.index(surface, search_from)
        end = start + len(surface)
        search_from = end
        entities.append(
            Entity(
                id=f"fir-001:entity:{index}",
                type=entity_type,
                label=surface,
                confidence=0.9,
                provenance=[
                    Provenance(document_id="fir-001", evidence_text=text, confidence=0.91)
                ],
                attributes={"fragment_index": 0, "start": start, "end": end},
            )
        )
    return document, entities


def _extract(
    text: str,
    mentions: list[tuple[str, str]],
    predictions: dict[tuple[str, str], tuple[str, float]],
):
    document, entities = _fixture(text, mentions)
    classifier = FakeClassifier(predictions)
    result = NarrativeRelationshipExtractor(classifier=classifier).extract_with_decisions(
        document, entities
    )
    return result, classifier


def test_default_classifier_is_lazy() -> None:
    extractor = NarrativeRelationshipExtractor()
    assert isinstance(extractor._classifier, DeBERTaRelationClassifier)
    assert extractor._classifier._model is None
    assert extractor._classifier._tokenizer is None


def test_valid_person_to_person_contacted_preserves_evidence_and_offsets() -> None:
    result, _ = _extract(
        "Rahul contacted Ahmed.",
        [("Rahul", "person"), ("Ahmed", "person")],
        {("Rahul", "Ahmed"): ("CONTACTED", 0.96)},
    )
    relationship = result.relationships[0]
    assert relationship.type == "CONTACTED"
    assert relationship.source_entity_id.endswith(":1")
    assert relationship.target_entity_id.endswith(":2")
    assert relationship.provenance[0].evidence_text == "Rahul contacted Ahmed."
    assert relationship.provenance[0].page_number == 2
    assert relationship.attributes["subject_start"] == 0
    assert relationship.attributes["object_start"] == 16
    assert relationship.attributes["model_version"] == "test"


def test_person_location_visited() -> None:
    result, _ = _extract(
        "Rahul travelled to Kochi.",
        [("Rahul", "person"), ("Kochi", "location")],
        {("Rahul", "Kochi"): ("VISITED", 0.94)},
    )
    assert [relationship.type for relationship in result.relationships] == ["VISITED"]


def test_person_location_located_at() -> None:
    result, _ = _extract(
        "Police observed Rahul at Kochi station.",
        [("Rahul", "person"), ("Kochi", "location")],
        {("Rahul", "Kochi"): ("LOCATED_AT", 0.93)},
    )
    assert [relationship.type for relationship in result.relationships] == ["LOCATED_AT"]


def test_person_account_transferred_to() -> None:
    result, _ = _extract(
        "Rahul transferred funds to ACCT-123456.",
        [("Rahul", "person"), ("ACCT-123456", "account_number")],
        {("Rahul", "ACCT-123456"): ("TRANSFERRED_TO", 0.98)},
    )
    assert [relationship.type for relationship in result.relationships] == ["TRANSFERRED_TO"]


def test_impossible_owns_vehicle_prediction_for_account_is_rejected() -> None:
    result, _ = _extract(
        "Rahul transferred funds to ACCT-123456.",
        [("Rahul", "person"), ("ACCT-123456", "account_number")],
        {("Rahul", "ACCT-123456"): ("OWNS_VEHICLE", 0.99)},
    )
    assert result.relationships == []
    decision = next(item for item in result.decisions if item.predicted_relation == "OWNS_VEHICLE")
    assert decision.accepted is False
    assert decision.rejection_reason == "predicted_relation_signature_mismatch"


def test_unsupported_type_pair_is_rejected_before_classification() -> None:
    result, classifier = _extract(
        "Kochi appears beside 9876543210 in the annexure.",
        [("Kochi", "location"), ("9876543210", "phone_number")],
        {},
    )
    assert classifier.calls == []
    assert result.relationships == []
    assert {decision.rejection_reason for decision in result.decisions} == {
        "unsupported_entity_signature"
    }


def test_explicit_negation_rejects_positive_prediction() -> None:
    result, _ = _extract(
        "Rahul did not contact Ahmed.",
        [("Rahul", "person"), ("Ahmed", "person")],
        {("Rahul", "Ahmed"): ("CONTACTED", 0.97)},
    )
    assert result.relationships == []
    decision = next(item for item in result.decisions if item.predicted_relation == "CONTACTED")
    assert decision.rejection_reason == "explicit_negation"


def test_does_not_establish_is_explicit_negation() -> None:
    result, _ = _extract(
        "The report does not establish that Suresh Menon contacted Rahul Kumar.",
        [("Suresh Menon", "person"), ("Rahul Kumar", "person")],
        {("Suresh Menon", "Rahul Kumar"): ("CONTACTED", 0.95)},
    )
    assert result.relationships == []
    decision = next(
        item for item in result.decisions if item.predicted_relation == "CONTACTED"
    )
    assert decision.rejection_reason == "explicit_negation"


def test_neighboring_negation_does_not_reject_a_positive_sentence() -> None:
    text = "Rahul did not contact Suresh. Ahmed was observed in Kochi."
    document, entities = _fixture(
        text,
        [
            ("Rahul", "person"),
            ("Suresh", "person"),
            ("Ahmed", "person"),
            ("Kochi", "location"),
        ],
    )
    classifier = FakeClassifier({("Ahmed", "Kochi"): ("LOCATED_AT", 0.94)})
    result = NarrativeRelationshipExtractor(classifier=classifier).extract_with_decisions(
        document, entities
    )

    accepted = next(item for item in result.decisions if item.accepted)
    assert accepted.predicted_relation == "LOCATED_AT"
    assert accepted.rejection_reason is None
    accepted_input = next(
        value
        for value in classifier.inputs
        if "SUBJECT [PERSON]: Ahmed" in value and "OBJECT [LOCATION]: Kochi" in value
    )
    assert "did not" not in accepted_input
    assert "<HEAD>Ahmed</HEAD> was observed in <TAIL>Kochi</TAIL>" in accepted_input


def test_reverse_direction_is_preserved() -> None:
    result, _ = _extract(
        "Ahmed contacted Rahul.",
        [("Ahmed", "person"), ("Rahul", "person")],
        {("Ahmed", "Rahul"): ("CONTACTED", 0.95)},
    )
    relationship = result.relationships[0]
    assert relationship.source_entity_id.endswith(":1")
    assert relationship.target_entity_id.endswith(":2")


def test_met_is_symmetric_and_deduplicated() -> None:
    result, _ = _extract(
        "Rahul met Ahmed.",
        [("Rahul", "person"), ("Ahmed", "person")],
        {
            ("Rahul", "Ahmed"): ("MET", 0.96),
            ("Ahmed", "Rahul"): ("MET", 0.95),
        },
    )
    assert len(result.relationships) == 1
    assert result.relationships[0].type == "MET"
    assert result.relationships[0].attributes["symmetric"] is True
    assert any(
        decision.rejection_reason == "duplicate_symmetric_relation"
        for decision in result.decisions
    )


def test_no_relation_never_becomes_relationship() -> None:
    result, _ = _extract(
        "Rahul and Ahmed were listed as witnesses.",
        [("Rahul", "person"), ("Ahmed", "person")],
        {
            ("Rahul", "Ahmed"): ("NO_RELATION", 0.92),
            ("Ahmed", "Rahul"): ("NO_RELATION", 0.91),
        },
    )
    assert result.relationships == []
    assert all(decision.rejection_reason == "no_relation" for decision in result.decisions)
