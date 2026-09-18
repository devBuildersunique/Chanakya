"""Chanakya backend application package."""

# Paddle's PIR compatibility flag must be set before any Paddle import.
from app.ocr_runtime import OCR_RUNTIME_SETTINGS

__all__ = ["OCR_RUNTIME_SETTINGS"]
