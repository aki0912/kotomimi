import json
from pathlib import Path

from kotomimi_eval.cli import build_parser, main


def test_dataset_list_json(capsys):
    assert main(["dataset", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row["dataset_id"] for row in payload["datasets"]} >= {"fleurs_ja", "common_voice_ja_26"}


def test_license_check_strict_succeeds(capsys):
    assert main(["license", "check", "fleurs_ja", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["allowed"] is True


def test_license_check_unknown_and_sharealike_fail_closed(capsys):
    assert main(["license", "check", "not_registered"]) == 2
    assert "DENY" in capsys.readouterr().out
    assert main(["license", "check", "cpjd"]) == 2
    assert "allow-sharealike" in capsys.readouterr().out


def test_license_check_sharealike_explicitly_succeeds(capsys):
    assert main(["license", "check", "cpjd", "--allow-sharealike"]) == 0
    assert "ALLOW" in capsys.readouterr().out


def test_license_check_requires_target(capsys):
    assert main(["license", "check"]) == 2
    assert "requires dataset IDs or --all" in capsys.readouterr().err


def test_common_voice_import_cli_requires_archive():
    try:
        main(["dataset", "import", "common_voice_ja_26"])
    except SystemExit as exc:
        assert exc.code == 2


def test_common_voice_api_dependency_degrades_clearly(tmp_path, monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def without_datacollective(name, *args, **kwargs):
        if name == "datacollective":
            raise ImportError("fixture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_datacollective)
    result = main([
        "dataset", "download", "common_voice_ja_26",
        "--data-root", str(Path(tmp_path) / "data"),
    ])
    assert result == 2
    assert "optional 'mdc' dependency" in capsys.readouterr().err


def test_audit_server_cli_defaults_to_loopback():
    args = build_parser().parse_args(["audit", "serve", "--latest"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
