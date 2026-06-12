"""Stream QCVN DOCX media into review-only storage using relationship IDs."""

from __future__ import annotations

import hashlib
import mimetypes
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SIGN_RE = re.compile(r"\b([PWRIS])[\s.-]?(\d{2,3}[a-z]?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedAsset:
    relationship_id: str
    source_locator: str | None
    source_member: str
    storage_key: str
    checksum: str
    mime_type: str
    asset_kind: str
    mapping_confidence: str
    sign_codes: tuple[str, ...]


def _normalize_sign_code(match: tuple[str, str]) -> str:
    return f"{match[0].upper()}.{match[1].lower()}"


def _relationship_targets(archive: zipfile.ZipFile) -> dict[str, str]:
    root = ElementTree.fromstring(archive.read("word/_rels/document.xml.rels"))
    targets: dict[str, str] = {}
    for relation in root.findall(f"{{{_REL_NS}}}Relationship"):
        relationship_id = relation.attrib.get("Id")
        target = relation.attrib.get("Target")
        if relationship_id and target and not target.startswith(("http:", "https:")):
            targets[relationship_id] = posixpath.normpath(
                posixpath.join("word", target)
            )
    return targets


def _drawing_contexts(archive: zipfile.ZipFile) -> dict[str, str]:
    root = ElementTree.fromstring(archive.read("word/document.xml"))
    contexts: dict[str, str] = {}
    for paragraph in root.iter(f"{{{_WORD_NS}}}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{{{_WORD_NS}}}t")).strip()
        for blip in paragraph.iter(f"{{{_DRAWING_NS}}}blip"):
            relationship_id = blip.attrib.get(f"{{{_OFFICE_REL_NS}}}embed")
            if relationship_id:
                contexts[relationship_id] = text
    return contexts


def extract_qcvn_assets(
    source_path: Path,
    destination_root: Path,
    document_key: str,
) -> list[ExtractedAsset]:
    """Extract media without loading the 95 MB DOCX or all images into memory."""
    destination_root = destination_root.resolve()
    target_dir = (destination_root / document_key).resolve()
    if not target_dir.is_relative_to(destination_root):
        raise ValueError("document_key tạo đường dẫn không an toàn")
    target_dir.mkdir(parents=True, exist_ok=True)

    records: list[ExtractedAsset] = []
    with zipfile.ZipFile(source_path) as archive:
        targets = _relationship_targets(archive)
        contexts = _drawing_contexts(archive)
        for relationship_id, member in targets.items():
            if not member.startswith("word/media/") or member not in archive.namelist():
                continue
            suffix = PurePosixPath(member).suffix.lower()
            safe_name = f"{relationship_id}{suffix}"
            destination = (target_dir / safe_name).resolve()
            if not destination.is_relative_to(target_dir):
                raise ValueError("tên asset không an toàn")

            digest = hashlib.sha256()
            with archive.open(member) as source, destination.open("wb") as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    target.write(chunk)

            context = contexts.get(relationship_id, "")
            codes = tuple(sorted({_normalize_sign_code(match) for match in _SIGN_RE.findall(context)}))
            records.append(
                ExtractedAsset(
                    relationship_id=relationship_id,
                    source_locator=context or None,
                    source_member=member,
                    storage_key=destination.relative_to(destination_root).as_posix(),
                    checksum=digest.hexdigest(),
                    mime_type=mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
                    asset_kind="sign_image" if len(codes) == 1 else "sign_group",
                    mapping_confidence="high" if len(codes) == 1 else "low",
                    sign_codes=codes,
                )
            )
    return records
