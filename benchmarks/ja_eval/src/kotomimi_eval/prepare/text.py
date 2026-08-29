from __future__ import annotations

import re
import unicodedata


def normalize_reference_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def normalize_reference_standard(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        char for char in value
        if not char.isspace()
        and not unicodedata.category(char).startswith(("P", "C"))
    )


def text_qc_flags(
    raw_text: str,
    eval_text: str,
    *,
    short_chars: int,
    long_chars: int,
    digit_heavy_ratio: float,
) -> list[str]:
    flags: list[str] = []
    if len(eval_text) <= short_chars:
        flags.append("very_short_text")
    if len(eval_text) > long_chars:
        flags.append("very_long_text")
    if "�" in raw_text:
        flags.append("replacement_char")
    if re.search(r"<[^>]+>", raw_text):
        flags.append("suspicious_markup")
    if re.search(r"(.)\1{4,}", eval_text):
        flags.append("repeated_chars")
    digit_count = sum(char.isascii() and char.isdigit() for char in eval_text)
    if eval_text and digit_count / len(eval_text) >= digit_heavy_ratio:
        flags.append("digit_heavy")
    if any(char.isascii() and char.isalpha() for char in raw_text):
        flags.append("latin_mixed")
    return flags


def has_forbidden_control(text: str) -> bool:
    return "\x00" in text or any(
        unicodedata.category(char) == "Cc" and char not in "\n\t\r"
        for char in text
    )
