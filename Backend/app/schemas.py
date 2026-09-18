"""Extensible graph-ready contracts for future document processing."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Traceability metadata for an extracted value."""

    document_id: str
    page_number: int | None = Field(default=None, ge=1)
    source_location: str | None = None
    evidence_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class TemporalInfo(BaseModel):
    """Known temporal values; extraction logic will populate these later."""

    event_start: datetime | None = None
    event_end: datetime | None = None
    observed_at: datetime | None = None
    recorded_at: datetime | None = None


class Entity(BaseModel):
    """A document-local entity suitable for downstream graph ingestion."""

    id: str
    type: str
    label: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance: list[Provenance] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A directed relationship between document-local entity identifiers."""

    id: str
    source_entity_id: str
    target_entity_id: str
    type: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    temporal: TemporalInfo | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class DocumentGraph(BaseModel):
    """Validated output contract for one processed source document."""

    document_id: str
    source_type: str | None = None
    temporal: TemporalInfo | None = None
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class ArtifactMetadata(BaseModel):
    """Safe metadata for one uploaded evidence artifact."""

    document_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=1)


class ProcessingMetadata(BaseModel):
    """Routing decisions made while processing an artifact."""

    input_format: str
    mode: str
    ocr_used: bool = False
    docres_used: bool = False
