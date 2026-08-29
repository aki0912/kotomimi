import json

from kotomimi_eval.cli import main


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
