from __future__ import annotations

import json
from pathlib import Path

from ..errors import ApprovalError


def load_approval(path: str | Path, dataset_id: str) -> dict:
    approval_path = Path(path)
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ApprovalError(f"manual approval file missing for {dataset_id}: {approval_path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalError(f"manual approval invalid for {dataset_id}: {approval_path.name}: {exc}") from exc
    if not isinstance(approval, dict) or approval.get("schema_version") != 1:
        raise ApprovalError(f"manual approval for {dataset_id} must use schema_version 1")
    if approval.get("dataset_id") != dataset_id:
        raise ApprovalError(f"manual approval dataset_id does not match {dataset_id}")
    for key in ("approved_by", "approved_at", "purpose"):
        if not isinstance(approval.get(key), str) or not approval[key].strip():
            raise ApprovalError(f"manual approval for {dataset_id} requires {key}")
    terms = approval.get("terms_reviewed")
    if not isinstance(terms, list) or not terms or any(not isinstance(term, str) for term in terms):
        raise ApprovalError(f"manual approval for {dataset_id} requires terms_reviewed")
    if not isinstance(approval.get("allow_redistribution"), bool):
        raise ApprovalError(f"manual approval for {dataset_id} requires allow_redistribution boolean")
    return approval
