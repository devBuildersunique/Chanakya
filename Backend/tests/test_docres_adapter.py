from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.docres_adapter import (
    DocResAdapter,
    DocResConfigurationError,
    DocResExecutionError,
    DocResTask,
)


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "DocRes"
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / "checkpoints").mkdir()
    (root / "checkpoints" / "docres.pkl").write_bytes(b"checkpoint")
    (root / "inference.py").write_text("# mocked by test\n", encoding="utf-8")
    return root


def _input(tmp_path: Path) -> Path:
    path = tmp_path / "scan.png"
    path.write_bytes(b"image")
    return path


def test_restore_uses_isolated_runtime_absolute_paths_and_default_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docres_root = _runtime(tmp_path)
    source = _input(tmp_path)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        output_directory = Path(command[command.index("--out_folder") + 1])
        (output_directory / "scan_deblurring.png").write_bytes(b"restored")
        return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = DocResAdapter(docres_root=docres_root, output_root=tmp_path / "outputs")

    result = adapter.restore(source)

    command, options = calls[0]
    assert result.task is DocResTask.DEBLURRING
    assert result.restored_path.is_file()
    assert result.restored_path.parent == result.output_directory
    assert result.input_path == source.resolve()
    assert Path(command[0]).is_absolute()
    assert Path(command[command.index("--im_path") + 1]).is_absolute()
    assert Path(command[command.index("--out_folder") + 1]).is_absolute()
    assert command[command.index("--task") + 1] == "deblurring"
    assert options["cwd"] == docres_root.resolve()
    assert options["shell"] is False


@pytest.mark.parametrize("task", list(DocResTask))
def test_restore_accepts_each_existing_docres_task(
    task: DocResTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _input(tmp_path)
    adapter = DocResAdapter(docres_root=_runtime(tmp_path), output_root=tmp_path / "outputs")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output_directory = Path(command[command.index("--out_folder") + 1])
        (output_directory / f"scan_{task.value}.png").write_bytes(b"restored")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert adapter.restore(source, task=task).task is task


def test_restore_rejects_unknown_task_before_subprocess(tmp_path: Path) -> None:
    adapter = DocResAdapter(docres_root=_runtime(tmp_path), output_root=tmp_path / "outputs")

    with pytest.raises(ValueError, match="Unsupported DocRes task"):
        adapter.restore(_input(tmp_path), task="unknown")


def test_restore_validates_input_and_python_executable(tmp_path: Path) -> None:
    docres_root = _runtime(tmp_path)
    adapter = DocResAdapter(docres_root=docres_root, output_root=tmp_path / "outputs")

    with pytest.raises(FileNotFoundError, match="input image"):
        adapter.restore(tmp_path / "missing.png")

    adapter.python_executable.unlink()
    with pytest.raises(DocResConfigurationError, match="Python executable"):
        adapter.restore(_input(tmp_path))


def test_restore_raises_clear_error_for_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = DocResAdapter(docres_root=_runtime(tmp_path), output_root=tmp_path / "outputs")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="CUDA unavailable")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(DocResExecutionError, match="exit code 2: CUDA unavailable"):
        adapter.restore(_input(tmp_path))


def test_restore_rejects_success_without_expected_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = DocResAdapter(docres_root=_runtime(tmp_path), output_root=tmp_path / "outputs")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
    )

    with pytest.raises(DocResExecutionError, match="did not create expected output"):
        adapter.restore(_input(tmp_path))


def test_restore_creates_unique_output_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = DocResAdapter(docres_root=_runtime(tmp_path), output_root=tmp_path / "outputs")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output_directory = Path(command[command.index("--out_folder") + 1])
        (output_directory / "scan_deblurring.png").write_bytes(b"restored")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = _input(tmp_path)

    first = adapter.restore(source)
    second = adapter.restore(source)

    assert first.output_directory != second.output_directory
