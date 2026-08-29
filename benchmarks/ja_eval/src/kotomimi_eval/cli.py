from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .errors import EvaluationConfigError, LicensePolicyError
from .licensing.policy import check_dataset_license
from .licensing.registry import load_registry
from .paths import APPROVAL_DIR


def _dataset_list(args: argparse.Namespace) -> int:
    registry = load_registry()
    rows = []
    for dataset_id in sorted(registry.datasets):
        record = registry.datasets[dataset_id]
        rows.append({
            "dataset_id": dataset_id,
            "display_name": record.display_name,
            "policy": record.license.policy,
            "spdx": record.license.spdx,
            "commercial_use": record.license.commercial_use,
            "acquisition": record.acquisition.get("mode", "unknown"),
            "gate": ({"strict": "eligible", "sharealike": "requires-opt-in",
                      "manual-review": "requires-approval"}[record.license.policy]),
        })
    if args.json:
        print(json.dumps({"schema_version": 1, "datasets": rows}, ensure_ascii=False, indent=2))
    else:
        print("dataset_id\tpolicy\tlicense\tgate\tacquisition\tname")
        for row in rows:
            print(f"{row['dataset_id']}\t{row['policy']}\t{row['spdx']}\t{row['gate']}\t"
                  f"{row['acquisition']}\t{row['display_name']}")
    return 0


def _approval_for(args: argparse.Namespace, dataset_id: str) -> Path | None:
    if args.approval is not None:
        return Path(args.approval)
    candidate = Path(args.approval_dir) / f"{dataset_id}.json"
    return candidate if candidate.is_file() else None


def _license_check(args: argparse.Namespace) -> int:
    registry = load_registry()
    if not args.all and not args.dataset_ids:
        raise EvaluationConfigError("license check requires dataset IDs or --all")
    if args.approval is not None and (args.all or len(args.dataset_ids) != 1):
        raise EvaluationConfigError("--approval can only be used with one dataset ID")
    dataset_ids = sorted(registry.datasets) if args.all else args.dataset_ids
    results = []
    failed = False
    for dataset_id in dataset_ids:
        try:
            record = registry.get(dataset_id)
            decision = check_dataset_license(
                record,
                allow_sharealike=args.allow_sharealike,
                approval_path=_approval_for(args, dataset_id),
            )
            result = asdict(decision)
        except LicensePolicyError as exc:
            failed = True
            result = {"dataset_id": dataset_id, "allowed": False, "reason": str(exc)}
        results.append(result)
    if args.json:
        print(json.dumps({"schema_version": 1, "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "ALLOW" if result["allowed"] else "DENY"
            print(f"{status}\t{result['dataset_id']}\t{result['reason']}")
    return 2 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kotomimi-eval")
    commands = parser.add_subparsers(dest="command", required=True)

    dataset = commands.add_parser("dataset", help="dataset registry operations")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_list = dataset_commands.add_parser("list", help="list registered datasets")
    dataset_list.add_argument("--json", action="store_true", help="emit JSON")
    dataset_list.set_defaults(handler=_dataset_list)

    license_parser = commands.add_parser("license", help="license policy operations")
    license_commands = license_parser.add_subparsers(dest="license_command", required=True)
    check = license_commands.add_parser("check", help="fail-closed dataset license check")
    check.add_argument("dataset_ids", nargs="*")
    check.add_argument("--all", action="store_true", help="check every registered dataset")
    check.add_argument("--allow-sharealike", action="store_true")
    check.add_argument("--approval", help="approval JSON for one manual-review dataset")
    check.add_argument("--approval-dir", default=str(APPROVAL_DIR))
    check.add_argument("--json", action="store_true", help="emit JSON")
    check.set_defaults(handler=_license_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except EvaluationConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
