import io
import tarfile

import pytest

from kotomimi_eval.errors import DatasetPreparationError
from kotomimi_eval.prepare.archives import extract_tar_safely


def _archive(path, members):
    with tarfile.open(path, "w:gz") as handle:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                info.size = 0
                handle.addfile(info)
            else:
                handle.addfile(info, io.BytesIO(data))


def test_safe_archive_extracts_regular_file(tmp_path):
    archive = tmp_path / "safe.tar.gz"
    _archive(archive, [("audio/example.wav", b"wave", "file")])
    files = extract_tar_safely(archive, tmp_path / "out")
    assert [path.relative_to(tmp_path / "out").as_posix() for path in files] == ["audio/example.wav"]
    assert files[0].read_bytes() == b"wave"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "audio\\escape.wav", "./dot.wav"])
def test_archive_path_traversal_is_rejected(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    _archive(archive, [(name, b"bad", "file")])
    with pytest.raises(DatasetPreparationError, match="archive member"):
        extract_tar_safely(archive, tmp_path / "out")


def test_archive_symlink_is_rejected(tmp_path):
    archive = tmp_path / "link.tar.gz"
    _archive(archive, [("link", b"", "symlink")])
    with pytest.raises(DatasetPreparationError, match="non-regular"):
        extract_tar_safely(archive, tmp_path / "out")


def test_archive_expanded_size_limit_is_enforced(tmp_path):
    archive = tmp_path / "large.tar.gz"
    _archive(archive, [("large.bin", b"12345", "file")])
    with pytest.raises(DatasetPreparationError, match="size exceeds"):
        extract_tar_safely(archive, tmp_path / "out", max_total_bytes=4)


def test_existing_same_size_but_changed_file_is_rejected(tmp_path):
    archive = tmp_path / "safe.tar.gz"
    _archive(archive, [("audio/example.wav", b"good", "file")])
    destination = tmp_path / "out"
    extract_tar_safely(archive, destination)
    (destination / "audio" / "example.wav").write_bytes(b"evil")
    with pytest.raises(DatasetPreparationError, match="refusing to overwrite"):
        extract_tar_safely(archive, destination)
