from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from .errors import (
    DatasetPreparationError,
    EvaluationConfigError,
    LicensePolicyError,
    ModelEvaluationUnavailable,
)
from .licensing.policy import check_dataset_license
from .licensing.registry import load_registry
from .paths import APPROVAL_DIR, DEFAULT_ARTIFACT_ROOT, DEFAULT_DATA_ROOT
from .suites import load_suites


def _display_path(path: str | Path) -> str:
    return Path(os.path.relpath(Path(path), Path.cwd())).as_posix()


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


def _dataset_download(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    if record.adapter == "fleurs":
        from .datasets.fleurs import download_fleurs

        receipt = download_fleurs(record, args.data_root)
        detail = f"revision={receipt['source_revision']}"
    elif record.adapter == "common_voice":
        from .datasets.common_voice import download_common_voice

        receipt = download_common_voice(record, args.data_root)
        detail = f"version={receipt['version']}"
    else:
        raise DatasetPreparationError(
            f"dataset download is not implemented for adapter {record.adapter!r}")
    print(f"downloaded {record.dataset_id} {detail}")
    return 0


def _dataset_import(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    if record.adapter != "common_voice":
        raise DatasetPreparationError(
            f"dataset import is not implemented for adapter {record.adapter!r}")
    from .datasets.common_voice import import_common_voice_archive

    receipt = import_common_voice_archive(record, args.data_root, args.archive)
    print(f"imported {record.dataset_id} version={receipt['version']} "
          f"sha256={receipt['archive']['sha256']}")
    return 0


def _dataset_prepare(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    if record.adapter == "fleurs":
        from .datasets.fleurs import prepare_fleurs

        prepared = prepare_fleurs(record, args.data_root)
    elif record.adapter == "common_voice":
        from .datasets.common_voice import prepare_common_voice

        prepared = prepare_common_voice(record, args.data_root)
    else:
        raise DatasetPreparationError(
            f"dataset prepare is not implemented for adapter {record.adapter!r}")
    print(f"prepared {prepared.dataset_id}: rows={prepared.row_count} "
          f"manifest_sha256={prepared.manifest_sha256}")
    return 0


def _dataset_verify(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    if record.adapter == "fleurs":
        from .datasets.fleurs import verify_prepared_fleurs

        prepared = verify_prepared_fleurs(record, args.data_root)
    elif record.adapter == "common_voice":
        from .datasets.common_voice import verify_prepared_common_voice

        prepared = verify_prepared_common_voice(record, args.data_root)
    else:
        raise DatasetPreparationError(
            f"dataset verify is not implemented for adapter {record.adapter!r}")
    print(f"verified {prepared.dataset_id}: rows={prepared.row_count} "
          f"manifest_sha256={prepared.manifest_sha256}")
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


def _suite_build(args: argparse.Namespace) -> int:
    registry = load_registry()
    suites = load_suites()
    try:
        suite = suites[args.suite]
    except KeyError as exc:
        raise EvaluationConfigError(f"unknown suite {args.suite!r}") from exc
    from .prepare.suite import build_suite

    manifest, lock = build_suite(
        suite, registry, args.data_root,
        allow_sharealike=args.allow_sharealike)
    print(f"built {suite.name}: manifest={_display_path(manifest)} lock={_display_path(lock)}")
    return 0


def _qc_run(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    from .qc.runner import run_qc

    report, report_dir = run_qc(record, args.data_root, args.artifact_root)
    print(f"QC {record.dataset_id}: official={report['views']['official']['rows']} "
          f"clean={report['views']['clean']['rows']} "
          f"hard_failures={len(report['hard_failures'])} "
          f"report={_display_path(report_dir)}")
    return 2 if report["hard_failures"] else 0


def _audit_create(args: argparse.Namespace) -> int:
    registry = load_registry()
    record = registry.get(args.dataset_id)
    from .audit.workflow import create_audit

    metadata, directory = create_audit(
        record, args.data_root, args.artifact_root, count=args.count, seed=args.seed)
    print(f"created audit {metadata['audit_id']}: samples={metadata['count']} "
          f"directory={_display_path(directory)}")
    return 0


def _latest_audit_id(artifact_root: str | Path) -> str:
    candidates = []
    for metadata_path in (Path(artifact_root) / "audits").glob("*/audit.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            candidates.append((metadata["created_at"], metadata["audit_id"]))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    if not candidates:
        raise EvaluationConfigError("no local audits exist")
    return max(candidates)[1]


def _selected_audit_id(args: argparse.Namespace) -> str:
    return _latest_audit_id(args.artifact_root) if args.latest else args.audit_id


def _audit_serve(args: argparse.Namespace) -> int:
    audit_id = _selected_audit_id(args)
    from .audit.server import serve_audit

    print(f"serving audit {audit_id} at http://{args.host}:{args.port}/")
    serve_audit(
        audit_id=audit_id,
        registry=load_registry(),
        data_root=args.data_root,
        artifact_root=args.artifact_root,
        host=args.host,
        port=args.port,
    )
    return 0


def _audit_status(args: argparse.Namespace) -> int:
    audit_id = _selected_audit_id(args)
    from .audit.workflow import load_audit_status

    status = load_audit_status(args.artifact_root, audit_id)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"audit {audit_id}: reviewed={status['reviewed']}/{status['total']} "
              f"remaining={status['remaining']} complete={status['complete']} "
              f"status={status['dataset_status']} "
              f"approved_for_gate={status['approved_for_gate']}")
    return 0


def _audit_report(args: argparse.Namespace) -> int:
    audit_id = _selected_audit_id(args)
    from .audit.workflow import write_audit_report

    report, directory = write_audit_report(args.artifact_root, audit_id)
    print(f"wrote audit report {audit_id}: status={report['dataset_status']} "
          f"directory={_display_path(directory)}")
    return 0


def _suite_verify(args: argparse.Namespace) -> int:
    suites = load_suites()
    try:
        suite = suites[args.suite]
    except KeyError as exc:
        raise EvaluationConfigError(f"unknown suite {args.suite!r}") from exc
    from .prepare.suite import verify_suite

    lock = verify_suite(suite, args.data_root)
    print(f"verified {suite.name}: manifest_sha256={lock['manifest_sha256']}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    if args.system != "hayamimi-ja":
        raise EvaluationConfigError(f"unknown evaluation system {args.system!r}")
    registry = load_registry()
    suites = load_suites()
    try:
        suite = suites[args.suite]
    except KeyError as exc:
        raise EvaluationConfigError(f"unknown suite {args.suite!r}") from exc
    from .evaluation.runner import evaluate_suite

    report, run_dir = evaluate_suite(
        suite=suite,
        registry=registry,
        data_root=args.data_root,
        artifact_root=args.artifact_root,
        threads=args.threads,
        punctuate=args.punctuate,
    )
    print(f"wrote {_display_path(run_dir)}")
    return 2 if report["failures"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kotomimi-eval")
    commands = parser.add_subparsers(dest="command", required=True)

    dataset = commands.add_parser("dataset", help="dataset registry operations")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_list = dataset_commands.add_parser("list", help="list registered datasets")
    dataset_list.add_argument("--json", action="store_true", help="emit JSON")
    dataset_list.set_defaults(handler=_dataset_list)
    for name, handler in (
        ("download", _dataset_download),
        ("prepare", _dataset_prepare),
        ("verify", _dataset_verify),
    ):
        command = dataset_commands.add_parser(name, help=f"{name} one registered dataset")
        command.add_argument("dataset_id")
        command.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
        command.set_defaults(handler=handler)
    dataset_import = dataset_commands.add_parser(
        "import", help="import one locally acquired dataset archive")
    dataset_import.add_argument("dataset_id")
    dataset_import.add_argument("--archive", required=True)
    dataset_import.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    dataset_import.set_defaults(handler=_dataset_import)

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

    qc_parser = commands.add_parser("qc", help="model-independent quality control")
    qc_commands = qc_parser.add_subparsers(dest="qc_command", required=True)
    qc_run = qc_commands.add_parser("run", help="build official and clean QC views")
    qc_run.add_argument("--dataset", dest="dataset_id", required=True)
    qc_run.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    qc_run.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    qc_run.set_defaults(handler=_qc_run)

    audit_parser = commands.add_parser("audit", help="persistent local human audit")
    audit_commands = audit_parser.add_subparsers(dest="audit_command", required=True)
    audit_create = audit_commands.add_parser("create", help="create a deterministic audit sample")
    audit_create.add_argument("--dataset", dest="dataset_id", required=True)
    audit_create.add_argument("--count", type=int, required=True)
    audit_create.add_argument("--seed", type=int, default=20260829)
    audit_create.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    audit_create.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    audit_create.set_defaults(handler=_audit_create)
    audit_serve = audit_commands.add_parser("serve", help="serve the loopback-only audit UI")
    audit_target = audit_serve.add_mutually_exclusive_group(required=True)
    audit_target.add_argument("--audit-id")
    audit_target.add_argument("--latest", action="store_true")
    audit_serve.add_argument("--host", default="127.0.0.1")
    audit_serve.add_argument("--port", type=int, default=8765)
    audit_serve.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    audit_serve.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    audit_serve.set_defaults(handler=_audit_serve)
    audit_status = audit_commands.add_parser("status", help="summarize persisted decisions")
    status_target = audit_status.add_mutually_exclusive_group(required=True)
    status_target.add_argument("--audit-id")
    status_target.add_argument("--latest", action="store_true")
    audit_status.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    audit_status.add_argument("--json", action="store_true")
    audit_status.set_defaults(handler=_audit_status)
    audit_report = audit_commands.add_parser("report", help="write a privacy-safe audit summary")
    report_target = audit_report.add_mutually_exclusive_group(required=True)
    report_target.add_argument("--audit-id")
    report_target.add_argument("--latest", action="store_true")
    audit_report.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    audit_report.set_defaults(handler=_audit_report)

    suite_parser = commands.add_parser("suite", help="deterministic suite operations")
    suite_commands = suite_parser.add_subparsers(dest="suite_command", required=True)
    suite_build = suite_commands.add_parser("build")
    suite_build.add_argument("suite")
    suite_build.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    suite_build.add_argument("--allow-sharealike", action="store_true")
    suite_build.set_defaults(handler=_suite_build)
    suite_verify = suite_commands.add_parser("verify")
    suite_verify.add_argument("suite")
    suite_verify.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    suite_verify.set_defaults(handler=_suite_verify)

    evaluate = commands.add_parser("evaluate", help="run an ASR system on a built suite")
    evaluate.add_argument("--suite", required=True)
    evaluate.add_argument("--system", default="hayamimi-ja")
    evaluate.add_argument("--threads", type=int, default=4)
    evaluate.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    evaluate.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    punctuation = evaluate.add_mutually_exclusive_group()
    punctuation.add_argument("--punctuate", dest="punctuate", action="store_true")
    punctuation.add_argument("--no-punctuate", dest="punctuate", action="store_false")
    evaluate.set_defaults(punctuate=False, handler=_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ModelEvaluationUnavailable as exc:
        print(f"integration evaluation skipped: {exc}", file=sys.stderr)
        return 3
    except (EvaluationConfigError, DatasetPreparationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
