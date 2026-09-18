import os
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pymupdf as fitz
import pytest
from pydantic import ValidationError

from app.ingestion import ingest_file
from app.ocr import OCRFragment, PaddleOCRService, _iter_lines
from app.ocr_runtime import OCRRuntimeSettings


def _ocr_result(text: str = "Police report", confidence: float = 0.97) -> list[dict[str, Any]]:
    return [
        {
            "rec_texts": [text],
            "rec_scores": [confidence],
            "rec_polys": [[[10, 20], [110, 20], [110, 40], [10, 40]]],
        }
    ]


def _write_png(path: Path) -> None:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 3), False)
    pixmap.clear_with(255)
    pixmap.save(path)


class FakePaddleEngine:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def predict(self, input: Any, **kwargs: Any) -> Any:
        self.calls.append((input, kwargs))
        return self.result


def test_runtime_workaround_is_applied_before_engine_creation(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    fake_module = ModuleType("paddleocr")

    class FakePaddleOCR:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def predict(self, input: Any, **kwargs: Any) -> list[Any]:
            return []

    fake_module.PaddleOCR = FakePaddleOCR
    monkeypatch.setitem(__import__("sys").modules, "paddleocr", fake_module)
    monkeypatch.setenv("FLAGS_enable_pir_api", "1")

    service = PaddleOCRService(
        runtime_settings=OCRRuntimeSettings(enable_pir_api=False, enable_mkldnn=False)
    )
    service._get_engine()

    assert os.environ["FLAGS_enable_pir_api"] == "0"
    assert captured["enable_mkldnn"] is False
    assert captured["use_doc_unwarping"] is False


def test_extract_image_preserves_evidence_provenance_and_dimensions(tmp_path: Path) -> None:
    image = tmp_path / "evidence.png"
    _write_png(image)
    engine = FakePaddleEngine(_ocr_result())

    result = PaddleOCRService(engine=engine).extract_image(image, document_id="image-001")

    fragment = result.fragments[0]
    assert result.text == "Police report"
    assert result.page_number is None
    assert (result.image_width, result.image_height) == (4, 3)
    assert fragment.document_id == "image-001"
    assert fragment.evidence_text == "Police report"
    assert fragment.confidence == 0.97
    assert fragment.bounding_box.points[0].model_dump() == {"x": 10.0, "y": 20.0}
    assert fragment.source_path == str(image.resolve())
    assert engine.calls == [(str(image), {})]


def test_pdf_ingestion_handoff_ocrs_only_textless_pages(tmp_path: Path) -> None:
    path = tmp_path / "mixed.pdf"
    pdf = fitz.open()
    native_page = pdf.new_page()
    native_page.insert_text((72, 72), "Native text")
    pdf.new_page()
    pdf.save(path)
    pdf.close()

    ingestion_result = ingest_file(path, document_id="mixed-001")
    engine = FakePaddleEngine(_ocr_result("Scanned page"))

    results = PaddleOCRService(engine=engine).extract_required_pdf_pages(path, ingestion_result)

    assert len(results) == 1
    assert results[0].page_number == 2
    assert results[0].text == "Scanned page"
    assert isinstance(engine.calls[0][0], np.ndarray)


def test_ocr_result_converts_to_shared_normalized_representation(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    _write_png(image)

    result = PaddleOCRService(engine=FakePaddleEngine(_ocr_result())).extract_page(
        image,
        document_id="fir-001",
        page_number=3,
    )
    normalized = result.to_normalized_fragments()[0]

    assert normalized.content == "Police report"
    assert normalized.original_value == "Police report"
    assert normalized.confidence == 0.97
    assert normalized.location.page_number == 3
    assert normalized.location.source_path == str(image.resolve())
    assert normalized.location.bounding_box == [
        (10.0, 20.0),
        (110.0, 20.0),
        (110.0, 40.0),
        (10.0, 40.0),
    ]


def test_extract_image_handles_no_detected_text(tmp_path: Path) -> None:
    image = tmp_path / "blank.png"
    _write_png(image)

    result = PaddleOCRService(engine=FakePaddleEngine([])).extract_image(
        image, document_id="blank-001"
    )

    assert result.fragments == []
    assert result.text == ""


def test_extract_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PaddleOCRService(engine=FakePaddleEngine([])).extract_image(
            tmp_path / "missing.png", document_id="missing-001"
        )


def test_parser_rejects_inconsistent_paddle_result_arrays() -> None:
    with pytest.raises(ValueError, match="inconsistent lengths"):
        _iter_lines([{"rec_texts": ["text"], "rec_scores": [], "rec_polys": []}])


def test_parser_rejects_invalid_polygon() -> None:
    with pytest.raises(ValueError, match="invalid text polygon"):
        _iter_lines(
            [{"rec_texts": ["text"], "rec_scores": [0.9], "rec_polys": [[[0, 0], [1, 1]]]}]
        )


def test_ocr_fragment_validates_confidence() -> None:
    with pytest.raises(ValidationError):
        OCRFragment.model_validate(
            {
                "document_id": "fir-001",
                "page_number": 1,
                "text": "text",
                "evidence_text": "text",
                "confidence": 1.1,
                "source_path": "page.png",
                "image_width": 10,
                "image_height": 10,
                "bounding_box": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 1, "y": 0},
                        {"x": 1, "y": 1},
                        {"x": 0, "y": 1},
                    ]
                },
            }
        )
