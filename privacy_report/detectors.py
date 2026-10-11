"""PII / secret detectors.

Each detector has a regex, an optional validator (to cut false positives),
a masking function (raw values NEVER reach the report), a GDPR-oriented
category and a base severity weight used by the risk model.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from typing import Callable, Optional


def luhn_ok(digits: str) -> bool:
    nums = [int(d) for d in re.sub(r"\D", "", digits)]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def iban_ok(value: str) -> bool:
    v = value.replace(" ", "").upper()
    if not 15 <= len(v) <= 34:
        return False
    rearranged = v[4:] + v[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def ip_is_public(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Private/loopback ranges are infrastructure, not people. Documentation
    # ranges (e.g. 203.0.113.0/24) are kept so demo data is detectable.
    return not (ip.is_private and not str(ip).startswith(("192.0.2.", "198.51.100.", "203.0.113.")))\
        and not ip.is_loopback and not ip.is_unspecified


# ---- masking helpers -------------------------------------------------------

def mask_email(v: str) -> str:
    local, _, domain = v.partition("@")
    d_name, _, tld = domain.rpartition(".")
    return f"{local[:1]}***@{d_name[:1]}***.{tld}"


def mask_keep_last(n: int) -> Callable[[str], str]:
    def _m(v: str) -> str:
        clean = re.sub(r"\s", "", v)
        return "•" * max(len(clean) - n, 3) + clean[-n:]
    return _m


def mask_ip(v: str) -> str:
    if ":" in v:
        return v.split(":")[0] + ":****:****"
    a, b, *_ = v.split(".")
    return f"{a}.{b}.x.x"


def mask_token(v: str) -> str:
    return v[:4] + "…[" + str(len(v)) + " chars]"


def mask_header(v: str) -> str:
    return re.sub(r"[A-Za-z0-9._~+/-]{16,}$", lambda m: m.group(0)[:4] + "…[redacted]", v)


def fingerprint(v: str) -> str:
    """Stable, non-reversible id so repeated values can be counted without storing them."""
    return hashlib.sha256(v.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Detector:
    key: str
    label: str
    category: str          # what a DPO would call it
    gdpr_note: str         # short legal context for the report
    weight: int            # 1 (low) .. 5 (critical)
    pattern: re.Pattern
    mask: Callable[[str], str]
    validator: Optional[Callable[[str], bool]] = None
    redact_regex: str = ""  # RE2-compatible regex for Alloy / OTel (no lookarounds)

    def find(self, line: str):
        for m in self.pattern.finditer(line):
            value = m.group(0).rstrip(" -")
            if self.validator and not self.validator(value):
                continue
            yield m.start(), m.start() + len(value), value


DETECTORS: list[Detector] = [
    Detector(
        "email", "Email address", "Direct identifier",
        "Personal data under GDPR Art. 4(1).", 3,
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
        mask_email,
        redact_regex=r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
    ),
    Detector(
        "card", "Payment card number", "Financial data (PCI DSS scope)",
        "Brings the log store into PCI DSS scope; also personal data.", 5,
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        mask_keep_last(4), validator=luhn_ok,
        redact_regex=r"\b(?:[0-9][ -]?){12,18}[0-9]\b",
    ),
    Detector(
        "iban", "IBAN / bank account", "Financial data",
        "Personal data; high misuse potential for fraud.", 4,
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        mask_keep_last(4), validator=iban_ok,
        redact_regex=r"\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b",
    ),
    Detector(
        "jwt", "JWT / session token", "Credential",
        "Not personal data by itself, but grants access to accounts that hold it.", 5,
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        mask_token,
        redact_regex=r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    ),
    Detector(
        "bearer", "Bearer / API key header", "Credential",
        "Credential exposure; rotate keys found in logs.", 5,
        re.compile(r"(?i)(?:authorization|x-api-key|api[_-]?key)[\"'=:\s]+(?:bearer\s+)?[A-Za-z0-9._~+/-]{16,}"),
        mask_header,
        redact_regex=r"(?i)(?:authorization|x-api-key|api[_-]?key)[\"'=: ]+(?:bearer )?[A-Za-z0-9._~+/-]{16,}",
    ),
    Detector(
        "aws_key", "AWS access key ID", "Credential",
        "Cloud credential; treat as a security incident.", 5,
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        mask_token,
        redact_regex=r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    ),
    Detector(
        "phone", "Phone number (E.164)", "Direct identifier",
        "Personal data under GDPR Art. 4(1).", 3,
        re.compile(r"(?<![\w+])\+[1-9]\d{7,14}\b"),
        mask_keep_last(2),
        redact_regex=r"\+[1-9][0-9]{7,14}\b",
    ),
    Detector(
        "ip", "Public IP address", "Online identifier",
        "Online identifier; CJEU Breyer (C-582/14) treats dynamic IPs as personal data.", 2,
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        mask_ip, validator=ip_is_public,
        redact_regex=r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
    ),
]

BY_KEY = {d.key: d for d in DETECTORS}

# Most specific first: a JWT must not also be counted as an email fragment,
# and IBAN digits must not be re-counted as a card number.
PRIORITY = ["jwt", "bearer", "aws_key", "email", "iban", "card", "phone", "ip"]


def scan_line(line: str, detectors: list[Detector]):
    """Return non-overlapping (detector, value) hits for one log line."""
    taken: list[tuple[int, int]] = []
    hits = []
    order = sorted(detectors, key=lambda d: PRIORITY.index(d.key) if d.key in PRIORITY else 99)
    for det in order:
        for start, end, value in det.find(line):
            if any(start < e and end > s for s, e in taken):
                continue
            taken.append((start, end))
            hits.append((det, value))
    return hits


def get_detectors(enabled: list[str] | None) -> list[Detector]:
    if not enabled:
        return DETECTORS
    return [BY_KEY[k] for k in enabled if k in BY_KEY]
