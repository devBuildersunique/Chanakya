"""FastAPI application for synchronous evidence processing."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from app.processing import EvidenceProcessingPipeline, ProcessingResponse, SUPPORTED_SUFFIXES

app = FastAPI(title="Chanakya API", version="0.1.0")
processing_pipeline = EvidenceProcessingPipeline()
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".csv": {"text/csv", "application/csv", "text/plain"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".json": {"application/json", "text/json"},
}


@app.get("/health")
def health() -> dict[str, str]:
    """Return a lightweight liveness response."""

    return {"status": "ok"}


@app.post("/process", response_model=ProcessingResponse)
async def process_artifact(
    artifact: UploadFile = File(...),
    use_docres: bool = Query(default=False),
) -> ProcessingResponse:
    """Process one validated evidence artifact synchronously."""

    safe_name = Path(artifact.filename or "").name
    suffix = Path(safe_name).suffix.lower()
    content_type = (artifact.content_type or "application/octet-stream").lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported file extension")
    allowed = _CONTENT_TYPES[suffix]
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail="File extension and content type do not match")
    if use_docres and suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="DocRes is only available for image uploads")

    document_id = f"{Path(safe_name).stem or 'artifact'}-{uuid.uuid4().hex[:12]}"
    try:
        with tempfile.TemporaryDirectory(prefix="chanakya-upload-") as directory:
            temporary_path = Path(directory) / f"artifact{suffix}"
            size = 0
            with temporary_path.open("wb") as target:
                while chunk := await artifact.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Upload exceeds 25 MiB limit")
                    target.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            return processing_pipeline.process(
                temporary_path,
                document_id=document_id,
                filename=safe_name,
                content_type=content_type,
                size_bytes=size,
                use_docres=use_docres,
            )
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=f"Unable to process artifact: {error}") from error
    finally:
        await artifact.close()
