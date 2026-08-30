from kotomimi_eval.prepare.text import (
    has_forbidden_control,
    normalize_reference_nfc,
    normalize_reference_standard,
    text_qc_flags,
)


def test_raw_nfc_and_standard_are_distinct():
    raw = "ＡＩは、iPhone 15です。"
    assert normalize_reference_nfc(raw) == raw
    assert normalize_reference_standard(raw) == "aiはiphone15です"


def test_standard_does_not_change_number_or_kana_form():
    assert normalize_reference_standard("二十円・カタカナ") == "二十円カタカナ"


def test_control_char_detection():
    assert has_forbidden_control("本文\x00")
    assert not has_forbidden_control("本文\n注記")


def test_text_qc_flags_do_not_mutate_reference():
    raw = "ABC123<noise>"
    flags = text_qc_flags(
        raw, normalize_reference_standard(raw),
        short_chars=1, long_chars=300, digit_heavy_ratio=0.2)
    assert raw == "ABC123<noise>"
    assert {"latin_mixed", "digit_heavy", "suspicious_markup"} <= set(flags)
