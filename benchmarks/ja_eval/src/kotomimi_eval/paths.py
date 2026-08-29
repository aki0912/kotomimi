from pathlib import Path


BENCHMARK_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BENCHMARK_ROOT.parents[1]
CONFIG_DIR = BENCHMARK_ROOT / "config"
SCHEMA_DIR = BENCHMARK_ROOT / "schemas"
APPROVAL_DIR = BENCHMARK_ROOT / "licenses" / "approvals"
DEFAULT_DATA_ROOT = BENCHMARK_ROOT / "data"
DEFAULT_ARTIFACT_ROOT = BENCHMARK_ROOT / "artifacts"
