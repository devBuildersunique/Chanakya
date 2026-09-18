"""Synchronous evidence-processing orchestration for the FastAPI boundary."""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.docres_adapter import DocResAdapter
from app.entity_extraction import GLiNEREntityExtractor
from app.ingestion import InputFormat, NormalizedDocument, NormalizedFragment, SourceLocation, ingest_file
from app.ocr import PaddleOCRService
from app.relationship_extraction import NarrativeRelationshipExtractor, RelationDecision
from app.schemas import ArtifactMetadata, Entity, ProcessingMetadata, Provenance, Relationship


NARRATIVE_SUFFIXES = frozenset({".pdf", ".docx", ".txt"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
STRUCTURED_SUFFIXES = frozenset({".csv", ".xlsx", ".json"})
SUPPORTED_SUFFIXES = NARRATIVE_SUFFIXES | IMAGE_SUFFIXES | STRUCTURED_SUFFIXES

_SCHEMA_MAPPINGS = (
    ("cdr", "CONTACTED", "phone_number", "phone_number", ("caller", "receiver")),
    ("cdr", "CONTACTED", "phone_number", "phone_number", ("caller", "callee")),
    ("cdr", "CONTACTED", "phone_number", "phone_number", ("caller_number", "receiver_number")),
    ("cdr", "CONTACTED", "phone_number", "phone_number", ("calling_number", "called_number")),
    ("transfer", "TRANSFERRED_TO", "account_number", "account_number", ("sender_account", "receiver_account")),
    ("transfer", "TRANSFERRED_TO", "account_number", "account_number", ("source_account", "destination_account")),
)


class ProcessingResponse(BaseModel):
    artifact: ArtifactMetadata
    processing: ProcessingMetadata
    fragments: list[NormalizedFragment] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    relation_decisions: list[RelationDecision] = Field(default_factory=list)


class ProcessingError(ValueError):
    """The uploaded artifact cannot be processed safely."""


class EvidenceProcessingPipeline:
    """Route one artifact without coupling structured data to NLP models."""

    def __init__(
        self,
        *,
        entity_extractor: Any | None = None,
        relationship_extractor: Any | None = None,
        ocr_service: Any | None = None,
        docres_adapter: Any | None = None,
    ) -> None:
        self.entity_extractor = entity_extractor or GLiNEREntityExtractor()
        self.relationship_extractor = relationship_extractor or NarrativeRelationshipExtractor()
        self.ocr_service = ocr_service or PaddleOCRService()
        self.docres_adapter = docres_adapter or DocResAdapter()

    def process(
        self,
        path: Path,
        *,
        document_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        use_docres: bool = False,
    ) -> ProcessingResponse:
        suffix = path.suffix.lower()
        artifact = ArtifactMetadata(
            document_id=document_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        if suffix in STRUCTURED_SUFFIXES:
            document = ingest_file(path, document_id=document_id)
            _identify_source(document, filename)
            entities, relationships = _extract_structured_relationships(document)
            return ProcessingResponse(
                artifact=artifact,
                processing=ProcessingMetadata(input_format=suffix[1:], mode="structured"),
                fragments=document.fragments,
                entities=entities,
                relationships=relationships,
            )

        docres_used = False
        if suffix in IMAGE_SUFFIXES:
            ocr_path = path
            restored_output: Path | None = None
            try:
                if use_docres:
                    restoration = self.docres_adapter.restore(path)
                    ocr_path = restoration.restored_path
                    restored_output = restoration.output_directory
                    docres_used = True
                page = self.ocr_service.extract_image(ocr_path, document_id=document_id)
                document = NormalizedDocument(
                    document_id=document_id,
                    format=InputFormat.IMAGE,
                    fragments=page.to_normalized_fragments(),
                )
            finally:
                if restored_output is not None:
                    shutil.rmtree(restored_output, ignore_errors=True)
            _identify_source(document, filename)
            return self._narrative_response(
                artifact, document, suffix[1:], ocr_used=True, docres_used=docres_used
            )

        document = ingest_file(path, document_id=document_id)
        ocr_used = False
        if document.format is InputFormat.PDF and document.pages_requiring_ocr:
            pages = self.ocr_service.extract_required_pdf_pages(path, document)
            for page in pages:
                document.fragments.extend(page.to_normalized_fragments())
            ocr_used = True
        _identify_source(document, filename)
        return self._narrative_response(
            artifact, document, suffix[1:], ocr_used=ocr_used, docres_used=False
        )

    def _narrative_response(
        self,
        artifact: ArtifactMetadata,
        document: NormalizedDocument,
        input_format: str,
        *,
        ocr_used: bool,
        docres_used: bool,
    ) -> ProcessingResponse:
        entities = self.entity_extractor.extract(document)
        result = self.relationship_extractor.extract_with_decisions(document, entities)
        relationships = [item for item in result.relationships if item.type != "NO_RELATION"]
        return ProcessingResponse(
            artifact=artifact,
            processing=ProcessingMetadata(
                input_format=input_format,
                mode="narrative",
                ocr_used=ocr_used,
                docres_used=docres_used,
            ),
            fragments=document.fragments,
            entities=entities,
            relationships=relationships,
            relation_decisions=result.decisions,
        )


def _identify_source(document: NormalizedDocument, filename: str) -> None:
    """Replace ephemeral upload paths with the stable artifact identifier."""

    for fragment in document.fragments:
        fragment.location.source_path = filename


def _normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _extract_structured_relationships(
    document: NormalizedDocument,
) -> tuple[list[Entity], list[Relationship]]:
    records = (
        _tabular_records(document.fragments)
        if document.format in {InputFormat.CSV, InputFormat.XLSX}
        else _json_records(document.fragments)
    )
    entities: list[Entity] = []
    relationships: list[Relationship] = []
    for record in records:
        mapping = _matching_mapping(record)
        if mapping is None:
            continue
        schema_name, relation_type, source_type, target_type, (source_key, target_key) = mapping
        source_fragment = record[source_key]
        target_fragment = record[target_key]
        if not str(source_fragment.content).strip() or not str(target_fragment.content).strip():
            continue
        source = _structured_entity(document, source_fragment, source_type, len(entities) + 1)
        entities.append(source)
        target = _structured_entity(document, target_fragment, target_type, len(entities) + 1)
        entities.append(target)
        location = {
            "source": source_fragment.location.model_dump(exclude_none=True),
            "target": target_fragment.location.model_dump(exclude_none=True),
        }
        evidence = f"{source_key}={source_fragment.content}; {target_key}={target_fragment.content}"
        relationships.append(
            Relationship(
                id=f"{document.document_id}:relationship:{len(relationships) + 1}",
                source_entity_id=source.id,
                target_entity_id=target.id,
                type=relation_type,
                confidence=1.0,
                provenance=[
                    Provenance(
                        document_id=document.document_id,
                        page_number=source_fragment.location.page_number,
                        source_location=json.dumps(location, ensure_ascii=False),
                        evidence_text=evidence,
                        confidence=1.0,
                    )
                ],
                attributes={
                    "deterministic": True,
                    "schema": schema_name,
                    "source_location": location["source"],
                    "target_location": location["target"],
                },
            )
        )
    return entities, relationships


def _structured_entity(
    document: NormalizedDocument,
    fragment: NormalizedFragment,
    entity_type: str,
    sequence: int,
) -> Entity:
    location = fragment.location.model_dump(exclude_none=True)
    return Entity(
        id=f"{document.document_id}:entity:{sequence}",
        type=entity_type,
        label=str(fragment.content),
        confidence=1.0,
        provenance=[
            Provenance(
                document_id=document.document_id,
                page_number=fragment.location.page_number,
                source_location=json.dumps(location, ensure_ascii=False),
                evidence_text=str(fragment.original_value),
                confidence=1.0,
            )
        ],
        attributes={"structured": True, "source_location": location},
    )


def _matching_mapping(
    record: Mapping[str, NormalizedFragment],
) -> tuple[str, str, str, str, tuple[str, str]] | None:
    for mapping in _SCHEMA_MAPPINGS:
        source_key, target_key = mapping[4]
        if source_key in record and target_key in record:
            return mapping
    return None


def _tabular_records(
    fragments: Iterable[NormalizedFragment],
) -> list[dict[str, NormalizedFragment]]:
    by_sheet: dict[str, dict[int, dict[int, NormalizedFragment]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for fragment in fragments:
        location = fragment.location
        if location.row_number is None or location.column_number is None:
            continue
        sheet = location.sheet_name or ""
        by_sheet[sheet][location.row_number][location.column_number] = fragment

    records: list[dict[str, NormalizedFragment]] = []
    for rows in by_sheet.values():
        if not rows:
            continue
        header_row_number = min(rows)
        headers = {
            column: _normalize_header(fragment.content)
            for column, fragment in rows[header_row_number].items()
        }
        if len(set(headers.values())) != len(headers):
            continue
        for row_number, cells in rows.items():
            if row_number == header_row_number:
                continue
            records.append(
                {
                    headers[column]: fragment
                    for column, fragment in cells.items()
                    if column in headers and headers[column]
                }
            )
    return records


def _json_records(
    fragments: Iterable[NormalizedFragment],
) -> list[dict[str, NormalizedFragment]]:
    records: dict[str, dict[str, NormalizedFragment]] = defaultdict(dict)
    pattern = re.compile(r'^(.*)(?:\["((?:\\.|[^"])*)"\])$')
    for fragment in fragments:
        path = fragment.location.json_path
        if not path:
            continue
        match = pattern.match(path)
        if not match:
            continue
        parent, raw_key = match.groups()
        try:
            key = json.loads(f'"{raw_key}"')
        except json.JSONDecodeError:
            continue
        records[parent][_normalize_header(key)] = fragment
    return list(records.values())
