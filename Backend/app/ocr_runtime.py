"""Process-level PaddleOCR runtime settings for the verified Windows CPU setup.

The PIR flag must be configured before PaddlePaddle is imported. Chanakya applies
the known-safe defaults itself, while allowing explicit deployment overrides via
``CHANAKYA_OCR_ENABLE_PIR_API`` and ``CHANAKYA_OCR_ENABLE_MKLDNN``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _read_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True, slots=True)
class OCRRuntimeSettings:
    enable_pir_api: bool = False
    enable_mkldnn: bool = False

    @classmethod
    def from_environment(cls) -> "OCRRuntimeSettings":
        return cls(
            enable_pir_api=_read_bool("CHANAKYA_OCR_ENABLE_PIR_API", False),
            enable_mkldnn=_read_bool("CHANAKYA_OCR_ENABLE_MKLDNN", False),
        )

    def apply_process_settings(self) -> None:
        """Set Paddle's targeted process flag before PaddlePaddle import."""

        os.environ["FLAGS_enable_pir_api"] = "1" if self.enable_pir_api else "0"


OCR_RUNTIME_SETTINGS = OCRRuntimeSettings.from_environment()
OCR_RUNTIME_SETTINGS.apply_process_settings()
