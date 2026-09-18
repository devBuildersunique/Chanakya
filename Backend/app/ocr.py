"""PaddleOCR 3.x adapter with document and page-level provenance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pymupdf as fitz
from pydantic import BaseModel, Field

from app.ingestion import InputFormat, NormalizedDocument, NormalizedFragment, SourceLocation
from app.ocr_runtime import OCR_RUNTIME_SETTINGS, OCRRuntimeSettings


class Point(BaseModel):
    x: float
    y: float


class BoundingBox(BaseModel):
    """OCR polygon in rendered-image pixel coordinates."""

    points: list[Point] = Field(min_length=4)


class OCRFragment(BaseModel):
    """Recognized text and the source evidence supporting it."""

    document_id: str
    page_number: int | None = Field(default=None, ge=1)
    text: str
    evidence_text: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox
    source_path: str
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)

    def to_normalized_fragment(self) -> NormalizedFragment:
        """Adapt OCR evidence to the shared Phase 2 representation."""

        return NormalizedFragment(
            content=self.text,
            original_value=self.evidence_text,
            confidence=self.confidence,
            location=SourceLocation(
                page_number=self.page_number,
                source_path=self.source_path,
                image_width=self.image_width,
                image_height=self.image_height,
                bounding_box=[(point.x, point.y) for point in self.bounding_box.points],
            ),
        )


class OCRPageResult(BaseModel):
    document_id: str
    page_number: int | None = Field(default=None, ge=1)
    source_path: str
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    fragments: list[OCRFragment] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Plain text suitable for later GLiNER/UIE input."""

        return "\n".join(fragment.text for fragment in self.fragments)

    def to_normalized_fragments(self) -> list[NormalizedFragment]:
        return [fragment.to_normalized_fragment() for fragment in self.fragments]


class OCREngine(Protocol):
    def predict(self, input: Any, **kwargs: Any) -> Any: ...


class PaddleOCRService:
    """Independent OCR boundary; a restoration step can later precede it."""

    def __init__(
        self,
        engine: OCREngine | None = None,
        *,
        lang: str = "en",
        runtime_settings: OCRRuntimeSettings | None = None,
    ) -> None:
        self._engine = engine
        self._lang = lang
        self._runtime_settings = runtime_settings or OCR_RUNTIME_SETTINGS

    def extract_image(
        self,
        image_path: str | Path,
        *,
        document_id: str,
        page_number: int | None = None,
    ) -> OCRPageResult:
        """OCR an image file without loading Paddle models until first use."""

        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        pixmap = fitz.Pixmap(str(path))
        width, height = pixmap.width, pixmap.height
        pixmap = None
        return self._extract(
            str(path),
            document_id=document_id,
            page_number=page_number,
            source_path=str(path.resolve()),
            image_width=width,
            image_height=height,
        )

    def extract_page(
        self,
        image_path: str | Path,
        *,
        document_id: str,
        page_number: int,
    ) -> OCRPageResult:
        """OCR a pre-rendered PDF page image."""

        return self.extract_image(image_path, document_id=document_id, page_number=page_number)

    def extract_pdf_page(
        self,
        pdf_path: str | Path,
        *,
        document_id: str,
        page_number: int,
        dpi: int = 200,
    ) -> OCRPageResult:
        """Render one 1-based PDF page in memory and OCR the rendered pixels."""

        if page_number < 1:
            raise ValueError("page_number must be at least 1")
        if dpi < 72:
            raise ValueError("dpi must be at least 72")

        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        with fitz.open(path) as pdf:
            if page_number > pdf.page_count:
                raise ValueError(f"page_number {page_number} exceeds PDF page count {pdf.page_count}")
            page = pdf.load_page(page_number - 1)
            pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            width, height = pixmap.width, pixmap.height

        return self._extract(
            image,
            document_id=document_id,
            page_number=page_number,
            source_path=str(path.resolve()),
            image_width=width,
            image_height=height,
        )

    def extract_required_pdf_pages(
        self,
        pdf_path: str | Path,
        ingestion_result: NormalizedDocument,
        *,
        dpi: int = 200,
    ) -> list[OCRPageResult]:
        """OCR only PDF pages that native ingestion marked as textless."""

        if ingestion_result.format is not InputFormat.PDF:
            raise ValueError("ingestion_result must represent a PDF")
        return [
            self.extract_pdf_page(
                pdf_path,
                document_id=ingestion_result.document_id,
                page_number=page_number,
                dpi=dpi,
            )
            for page_number in ingestion_result.pages_requiring_ocr
        ]

    def _extract(
        self,
        image: Any,
        *,
        document_id: str,
        page_number: int | None,
        source_path: str,
        image_width: int,
        image_height: int,
    ) -> OCRPageResult:
        raw_result = self._get_engine().predict(image)
        fragments = [
            OCRFragment(
                document_id=document_id,
                page_number=page_number,
                text=text,
                evidence_text=text,
                confidence=confidence,
                bounding_box=BoundingBox(
                    points=[Point(x=float(point[0]), y=float(point[1])) for point in polygon]
                ),
                source_path=source_path,
                image_width=image_width,
                image_height=image_height,
            )
            for polygon, text, confidence in _iter_lines(raw_result)
            if text.strip()
        ]
        return OCRPageResult(
            document_id=document_id,
            page_number=page_number,
            source_path=source_path,
            image_width=image_width,
            image_height=image_height,
            fragments=fragments,
        )

    def _get_engine(self) -> OCREngine:
        if self._engine is None:
            self._runtime_settings.apply_process_settings()
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                lang=self._lang,
                enable_mkldnn=self._runtime_settings.enable_mkldnn,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        return self._engine


def _iter_lines(raw_result: Any) -> list[tuple[Sequence[Sequence[float]], str, float]]:
    """Normalize PaddleOCR 3.x results into polygon/text/confidence tuples."""

    if not raw_result:
        return []

    lines: list[tuple[Sequence[Sequence[float]], str, float]] = []
    for result in raw_result:
        data = _result_mapping(result)
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        polygons = data.get("rec_polys", [])
        if not (len(texts) == len(scores) == len(polygons)):
            raise ValueError("PaddleOCR result arrays have inconsistent lengths")
        for polygon, text, confidence in zip(polygons, texts, scores, strict=True):
            if len(polygon) < 4 or any(len(point) < 2 for point in polygon):
                raise ValueError("PaddleOCR returned an invalid text polygon")
            lines.append((polygon, str(text), float(confidence)))
    return lines


def _result_mapping(result: Any) -> Mapping[str, Any]:
    if isinstance(result, Mapping):
        return result
    json_value = getattr(result, "json", None)
    if isinstance(json_value, Mapping):
        return json_value.get("res", json_value)
    raise ValueError("Unexpected PaddleOCR 3.x result type")
