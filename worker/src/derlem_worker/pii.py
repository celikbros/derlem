from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable


ProgressCallback = Callable[[dict[str, int]], None]
PROGRESS_INTERVAL_BYTES = 64 * 1024 * 1024


EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![\w.-])", re.IGNORECASE)
TCKN_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")
IBAN_PATTERN = re.compile(r"(?<![A-Z0-9])TR(?:[ ]?\d){24}(?![A-Z0-9])", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?90[\s().-]*)?0?5\d{2}(?:[\s().-]*\d){7}(?!\d)")
CARD_PATTERN = re.compile(r"(?<![A-Z0-9])(?:\d[ -]?){13,19}(?![\d -])", re.IGNORECASE)
PII_KEYS = ("tckn", "iban", "email", "phone", "payment_card")


@dataclass(frozen=True)
class PIIReport:
    scanner_version: str
    findings: dict[str, int]

    @property
    def status(self) -> str:
        return "flagged" if any(self.findings.values()) else "clear"


class PIIScanner:
    version = "basic-tr-v1"

    def scan_file(
        self,
        path: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        progress_interval_bytes: int = PROGRESS_INTERVAL_BYTES,
    ) -> PIIReport:
        if progress_interval_bytes <= 0:
            raise ValueError("progress_interval_bytes must be positive")
        counts: Counter[str] = Counter()
        total_bytes = path.stat().st_size
        bytes_processed = 0
        lines_read = 0
        next_progress_at = progress_interval_bytes
        last_reported_bytes = -1
        with path.open("rb") as source:
            for raw_line in source:
                bytes_processed += len(raw_line)
                lines_read += 1
                counts.update(count_pii_in_text(raw_line.decode("utf-8")))
                if progress_callback is not None and bytes_processed >= next_progress_at:
                    progress_callback(
                        {
                            "input_bytes_processed": bytes_processed,
                            "input_bytes_total": total_bytes,
                            "lines_read": lines_read,
                            "findings_count": sum(counts.values()),
                        }
                    )
                    last_reported_bytes = bytes_processed
                    while next_progress_at <= bytes_processed:
                        next_progress_at += progress_interval_bytes

        if progress_callback is not None and bytes_processed != last_reported_bytes:
            progress_callback(
                {
                    "input_bytes_processed": bytes_processed,
                    "input_bytes_total": total_bytes,
                    "lines_read": lines_read,
                    "findings_count": sum(counts.values()),
                }
            )

        findings = {
            key: counts.get(key, 0)
            for key in PII_KEYS
        }
        return PIIReport(scanner_version=self.version, findings=findings)


def count_pii_in_text(text: str) -> dict[str, int]:
    return {
        "tckn": sum(is_valid_tckn(value) for value in TCKN_PATTERN.findall(text)),
        "iban": sum(is_valid_iban(value) for value in IBAN_PATTERN.findall(text)),
        "email": len(EMAIL_PATTERN.findall(text)),
        "phone": sum(is_valid_tr_phone(value) for value in PHONE_PATTERN.findall(text)),
        "payment_card": sum(is_valid_luhn(value) for value in CARD_PATTERN.findall(text)),
    }


def is_valid_tckn(value: str) -> bool:
    if len(value) != 11 or not value.isdigit() or value[0] == "0":
        return False
    digits = [int(digit) for digit in value]
    odd_sum = sum(digits[index] for index in (0, 2, 4, 6, 8))
    even_sum = sum(digits[index] for index in (1, 3, 5, 7))
    tenth = ((odd_sum * 7) - even_sum) % 10
    eleventh = sum(digits[:10]) % 10
    return digits[9] == tenth and digits[10] == eleventh


def is_valid_iban(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).upper()
    if len(compact) != 26 or not compact.startswith("TR") or not compact[2:].isdigit():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(character) - 55) if character.isalpha() else character for character in rearranged)
    remainder = 0
    for character in numeric:
        remainder = (remainder * 10 + int(character)) % 97
    return remainder == 1


def is_valid_tr_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("90"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits.startswith("5")


def is_valid_luhn(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0
