"""Validate raw documents before staging ingestion."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = _BACKEND_ROOT / "storage" / "raw"
DEFAULT_MANIFEST = _BACKEND_ROOT / "storage" / "raw_documents_manifest.yaml"
_MAX_ARCHIVE_RATIO = 250
_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_SUPPORTED_SUFFIXES = {".docx", ".pdf"}


@dataclass
class InventoryReport:
    valid_files: list[str] = field(default_factory=list)
    ignored_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    # JSON is a strict YAML subset, keeping this file dependency-free.
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_docx_archive(path: Path) -> str | None:
    if not zipfile.is_zipfile(path):
        return "not a valid DOCX/ZIP archive"
    with zipfile.ZipFile(path) as archive:
        total_compressed = sum(item.compress_size for item in archive.infolist()) or 1
        total_uncompressed = sum(item.file_size for item in archive.infolist())
        if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
            return "uncompressed data exceeds 512 MB"
        if total_uncompressed / total_compressed > _MAX_ARCHIVE_RATIO:
            return "suspicious compression ratio"
        if "word/document.xml" not in archive.namelist():
            return "missing word/document.xml"
    return None


def validate_raw_inventory(
    raw_dir: Path = DEFAULT_RAW_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> InventoryReport:
    """Validate files that actually exist under ``storage/raw``.

    The manifest is now metadata, not the complete inventory lock. Missing
    manifest files are warnings so a partial storage snapshot can still be
    staged, while present DOCX/PDF files that are not listed in the manifest are
    accepted with inferred metadata for HITL review.
    """
    report = InventoryReport()
    manifest = load_manifest(manifest_path)
    expected = {item["filename"]: item for item in manifest["documents"]}

    seen_files: set[str] = set()
    for path in sorted(raw_dir.iterdir(), key=lambda item: item.name.lower()):
        if path.name == ".gitkeep" or path.name.startswith("~$"):
            report.ignored_files.append(path.name)
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            report.ignored_files.append(path.name)
            continue

        entry = expected.get(path.name)
        if path.suffix.lower() == ".docx":
            archive_error = _validate_docx_archive(path)
            if archive_error:
                report.errors.append(f"{path.name}: {archive_error}")
                continue

        checksum = sha256_file(path)
        if entry is not None and checksum != entry["sha256"]:
            report.errors.append(f"{path.name}: checksum does not match manifest")
            continue

        if entry is None:
            report.warnings.append(
                f"{path.name}: not listed in manifest; staging with inferred metadata"
            )
        report.valid_files.append(path.name)
        seen_files.add(path.name)

    missing = sorted(set(expected) - seen_files)
    report.warnings.extend(f"{name}: missing from storage/raw" for name in missing)
    return report


if __name__ == "__main__":
    result = validate_raw_inventory()
    print(json.dumps(result.__dict__ | {"ok": result.ok}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.ok else 1)
