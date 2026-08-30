from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from ..errors import LicensePolicyError
from .approvals import load_approval
from .registry import DatasetRecord


STRICT_SPDX = frozenset({"CC0-1.0", "CC-BY-4.0"})
SHAREALIKE_SPDX = frozenset({"CC-BY-SA-4.0"})
STRICT_OPERATIONAL_RESTRICTIONS = frozenset({
    "no_speaker_reidentification", "no_rehosting", "no_resharing",
})
FORBIDDEN_MARKERS = (
    "-NC", "NON-COMMERCIAL", "NONCOMMERCIAL", "RESEARCH-ONLY",
    "RESEARCH_ONLY", "ARTICLE-30-4", "ARTICLE_30_4", "30条の4",
)


@dataclass(frozen=True)
class LicenseDecision:
    dataset_id: str
    allowed: bool
    policy: str
    spdx: str
    reason: str
    approval_used: bool = False


def _reject(record: DatasetRecord, reason: str) -> LicensePolicyError:
    return LicensePolicyError(f"dataset {record.dataset_id!r} rejected: {reason}")


def check_dataset_license(
    record: DatasetRecord,
    *,
    allow_sharealike: bool = False,
    approval_path: str | Path | None = None,
) -> LicenseDecision:
    license_info = record.license
    if not record.source_url:
        raise _reject(record, "source URL is required")
    if license_info.commercial_use is not True:
        raise _reject(record, "commercial_use must be explicitly true")
    searchable = " ".join((license_info.spdx, *license_info.restrictions,
                           *license_info.additional_terms)).upper()
    if any(marker in searchable for marker in FORBIDDEN_MARKERS):
        raise _reject(record, "non-commercial, research-only, or Article 30-4 terms are forbidden")

    approval_used = False
    if license_info.policy == "strict":
        if license_info.spdx not in STRICT_SPDX:
            raise _reject(record, f"SPDX {license_info.spdx} is not allowed for strict policy")
        if license_info.share_alike:
            raise _reject(record, "strict policy cannot declare share_alike")
        if license_info.additional_terms:
            raise _reject(record, "additional terms require manual-review policy")
        unknown_restrictions = set(license_info.restrictions) - STRICT_OPERATIONAL_RESTRICTIONS
        if unknown_restrictions:
            raise _reject(record, "unreviewed restrictions require manual-review policy")
    elif license_info.policy == "sharealike":
        if license_info.spdx not in SHAREALIKE_SPDX or not license_info.share_alike:
            raise _reject(record, "sharealike policy requires CC-BY-SA-4.0 and share_alike=true")
        if license_info.additional_terms or license_info.restrictions:
            raise _reject(record, "additional sharealike terms require separate manual review")
        if not allow_sharealike:
            raise _reject(record, "explicit --allow-sharealike is required")
    elif license_info.policy == "manual-review":
        if license_info.spdx not in STRICT_SPDX:
            raise _reject(record, f"manual approval cannot override SPDX {license_info.spdx}")
        if approval_path is None:
            raise _reject(record, "a local approval JSON is required")
        approval = load_approval(approval_path, record.dataset_id)
        normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
        reviewed = {normalize(term) for term in approval["terms_reviewed"]}
        required = {normalize(license_info.spdx), *(
            normalize(term) for term in license_info.additional_terms)}
        missing = required - reviewed
        if missing:
            raise _reject(record, "manual approval does not cover every registered term")
        approval_used = True
    else:
        raise _reject(record, f"unknown policy {license_info.policy!r}")

    return LicenseDecision(
        dataset_id=record.dataset_id,
        allowed=True,
        policy=license_info.policy,
        spdx=license_info.spdx,
        reason="license policy satisfied",
        approval_used=approval_used,
    )
