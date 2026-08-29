from pathlib import Path, PurePosixPath


BENCHMARK_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BENCHMARK_ROOT.parents[1]
CONFIG_DIR = BENCHMARK_ROOT / "config"
SCHEMA_DIR = BENCHMARK_ROOT / "schemas"
APPROVAL_DIR = BENCHMARK_ROOT / "licenses" / "approvals"
DEFAULT_DATA_ROOT = BENCHMARK_ROOT / "data"
DEFAULT_ARTIFACT_ROOT = BENCHMARK_ROOT / "artifacts"


def safe_relative_parts(value: object) -> tuple[str, ...]:
    """Return portable POSIX path parts or reject absolute/traversal syntax."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path is not a portable relative path")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("path is not a portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("path is not a portable relative path")
    return path.parts
