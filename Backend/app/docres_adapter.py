"""Isolated subprocess boundary for the DocRes Python 3.10 runtime."""

from __future__ import annotations

import subprocess
import tempfile
from enum import StrEnum
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field


class DocResTask(StrEnum):
    DEWARPING = "dewarping"
    DESHADOWING = "deshadowing"
    APPEARANCE = "appearance"
    DEBLURRING = "deblurring"
    BINARIZATION = "binarization"
    END2END = "end2end"


class DocResExecutionResult(BaseModel):
    input_path: Path
    restored_path: Path
    output_directory: Path
    task: DocResTask
    return_code: int
    duration_seconds: float = Field(ge=0)
    stdout: str
    stderr: str


class DocResError(RuntimeError):
    """Base error for DocRes adapter failures."""


class DocResConfigurationError(DocResError):
    """Raised when the isolated DocRes runtime is incomplete."""


class DocResExecutionError(DocResError):
    """Raised when DocRes exits unsuccessfully or produces no image."""


class DocResAdapter:
    """Run DocRes without importing its Python 3.10-only dependencies."""

    def __init__(
        self,
        *,
        docres_root: str | Path | None = None,
        output_root: str | Path | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self.docres_root = Path(docres_root or project_root / "DocRes").resolve()
        default_output_root = Path(tempfile.gettempdir()) / "chanakya-docres"
        self.output_root = Path(output_root or default_output_root).resolve()
        self.timeout_seconds = timeout_seconds

    @property
    def python_executable(self) -> Path:
        return self.docres_root / ".venv" / "Scripts" / "python.exe"

    @property
    def inference_script(self) -> Path:
        return self.docres_root / "inference.py"

    @property
    def model_checkpoint(self) -> Path:
        return self.docres_root / "checkpoints" / "docres.pkl"

    def restore(
        self,
        input_path: str | Path,
        *,
        task: DocResTask | str = DocResTask.DEBLURRING,
    ) -> DocResExecutionResult:
        """Restore one image and return its validated output path and metadata."""

        source = Path(input_path).resolve()
        selected_task = self._validate_task(task)
        self._validate_runtime(source)

        self.output_root.mkdir(parents=True, exist_ok=True)
        output_directory = Path(
            tempfile.mkdtemp(prefix="docres-", dir=self.output_root)
        ).resolve()
        expected_output = output_directory / self._output_name(source, selected_task)
        command = [
            str(self.python_executable),
            str(self.inference_script),
            "--model_path",
            str(self.model_checkpoint),
            "--im_path",
            str(source),
            "--out_folder",
            str(output_directory),
            "--task",
            selected_task.value,
            "--save_dtsprompt",
            "0",
        ]

        started_at = perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=self.docres_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise DocResExecutionError(
                f"DocRes timed out after {self.timeout_seconds} seconds; output directory: "
                f"{output_directory}"
            ) from error
        except OSError as error:
            raise DocResExecutionError(f"Unable to start DocRes: {error}") from error

        duration_seconds = perf_counter() - started_at
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "no process output"
            raise DocResExecutionError(
                f"DocRes failed with exit code {completed.returncode}: {detail}"
            )
        if not expected_output.is_file():
            raise DocResExecutionError(
                f"DocRes exited successfully but did not create expected output: {expected_output}"
            )

        return DocResExecutionResult(
            input_path=source,
            restored_path=expected_output,
            output_directory=output_directory,
            task=selected_task,
            return_code=completed.returncode,
            duration_seconds=duration_seconds,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _validate_runtime(self, source: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"DocRes input image does not exist: {source}")
        if not source.suffix:
            raise ValueError("DocRes input image must have a file extension")
        if not self.python_executable.is_file():
            raise DocResConfigurationError(
                f"DocRes Python executable does not exist: {self.python_executable}"
            )
        if not self.inference_script.is_file():
            raise DocResConfigurationError(
                f"DocRes inference entry point does not exist: {self.inference_script}"
            )
        if not self.model_checkpoint.is_file():
            raise DocResConfigurationError(
                f"DocRes model checkpoint does not exist: {self.model_checkpoint}"
            )

    @staticmethod
    def _validate_task(task: DocResTask | str) -> DocResTask:
        try:
            return DocResTask(task)
        except ValueError as error:
            supported = ", ".join(item.value for item in DocResTask)
            raise ValueError(f"Unsupported DocRes task {task!r}; expected one of: {supported}") from error

    @staticmethod
    def _output_name(source: Path, task: DocResTask) -> str:
        return f"{source.stem}_{task.value}{source.suffix}"
