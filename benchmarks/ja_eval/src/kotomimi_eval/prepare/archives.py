from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import hashlib

from ..errors import DatasetPreparationError


def _safe_member_path(name: str) -> PurePosixPath:
    if "\\" in name:
        raise DatasetPreparationError(f"archive member uses a backslash path: {name!r}")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise DatasetPreparationError(f"unsafe archive member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise DatasetPreparationError(f"unsafe archive member path: {name!r}")
    return path


def extract_tar_safely(
    archive: str | Path,
    destination: str | Path,
    *,
    max_total_bytes: int = 5 * 1024**3,
    max_members: int = 100_000,
) -> list[Path]:
    """Extract regular files without traversal, links, devices, or overwrite."""
    archive_path = Path(archive)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total = 0
    with tarfile.open(archive_path, "r:*") as handle:
        members = handle.getmembers()
        if len(members) > max_members:
            raise DatasetPreparationError("archive member count exceeds safety limit")
        for member in members:
            if member.isdir():
                # POSIX tar writers commonly append a slash to directory names.
                # Validate the meaningful path without treating that marker as
                # an empty traversal component.
                member_path = _safe_member_path(member.name.rstrip("/"))
                destination_path.joinpath(*member_path.parts).mkdir(
                    parents=True, exist_ok=True)
                continue
            member_path = _safe_member_path(member.name)
            if not member.isfile() or member.issym() or member.islnk():
                raise DatasetPreparationError(f"archive contains a non-regular member: {member.name!r}")
            total += member.size
            if total > max_total_bytes:
                raise DatasetPreparationError("archive expanded size exceeds safety limit")
            output = destination_path.joinpath(*member_path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            source = handle.extractfile(member)
            if source is None:
                raise DatasetPreparationError(f"cannot read archive member: {member.name!r}")
            if output.exists():
                source_hash = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    source_hash.update(chunk)
                output_hash = hashlib.sha256()
                with output.open("rb") as existing:
                    for chunk in iter(lambda: existing.read(1024 * 1024), b""):
                        output_hash.update(chunk)
                if (output.stat().st_size == member.size
                        and source_hash.digest() == output_hash.digest()):
                    extracted.append(output)
                    continue
                raise DatasetPreparationError(f"refusing to overwrite extracted member: {member.name!r}")
            part = output.with_name(output.name + ".part")
            try:
                if part.exists():
                    part.unlink()
                with source, part.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                if part.stat().st_size != member.size:
                    raise DatasetPreparationError(f"archive member size mismatch: {member.name!r}")
                os.replace(part, output)
            finally:
                if part.exists():
                    part.unlink()
            extracted.append(output)
    return extracted
