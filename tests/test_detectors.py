import re

from privacy_report.detectors import BY_KEY, DETECTORS, iban_ok, luhn_ok, scan_line


def keys(line):
    return sorted(d.key for d, _ in scan_line(line, DETECTORS))


def test_validators():
    assert luhn_ok("4111 1111 1111 1111")
    assert not luhn_ok("1234567812345678")
    assert iban_ok("DE89370400440532013000")
    assert not iban_ok("DE00370400440532013000")


def test_order_id_is_not_a_card():
    assert "card" not in keys("order_id=1234567812345678 status=paid")


def test_private_ips_ignored_public_reported():
    assert keys("upstream=10.1.2.3") == []
    assert keys("client=203.0.113.9") == ["ip"]


def test_no_double_counting():
    line = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlLWZha2U"
    assert keys(line) == ["jwt"]


def test_masking_never_returns_raw_value():
    raw = {"email": "anna.smith@example.com", "card": "4111111111111111", "phone": "+37491234567"}
    for k, v in raw.items():
        assert v not in BY_KEY[k].mask(v)


def test_redaction_regexes_are_re2_friendly():
    for d in DETECTORS:
        assert "(?=" not in d.redact_regex and "(?<" not in d.redact_regex, d.key
        assert "(" not in d.redact_regex.replace("(?:", "").replace("(?i)", ""), d.key  # single capture group added later
        re.compile(d.redact_regex)
