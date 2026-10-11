"""Scan streams, aggregate hits per (stream, detector), score risk.

Output is a plain dict (also written to findings.json) so the DOCX renderer,
a CI gate, or a Grafana annotation pusher can all consume the same data.
Raw PII never leaves this module: only masked examples + fingerprints.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .detectors import Detector, fingerprint, scan_line

SEVERITY_BANDS = [(20, "Critical"), (12, "High"), (6, "Medium"), (0, "Low")]


def parse_duration_days(value: str) -> float:
    m = re.fullmatch(r"(\d+)([hdwy])", value.strip())
    if not m:
        raise ValueError(f"bad duration: {value}")
    n, unit = int(m.group(1)), m.group(2)
    return {"h": n / 24, "d": n, "w": n * 7, "y": n * 365}[unit]


def volume_factor(per_day: float) -> int:
    return 1 if per_day < 100 else 2 if per_day < 10_000 else 3


def retention_factor(days: float) -> float:
    return 1.0 if days <= 7 else 1.5 if days <= 30 else 2.0


def band(score: float) -> str:
    for threshold, name in SEVERITY_BANDS:
        if score >= threshold:
            return name
    return "Low"


def risk(det: Detector, per_day: float, retention_days: float) -> tuple[float, str]:
    score = round(det.weight * volume_factor(per_day) * retention_factor(retention_days), 1)
    return score, band(score)


def analyse_stream(selector: str, lines, total_lines_window: int, window_days: float,
                   detectors: list[Detector], retention_days: float, owner: str = "") -> list[dict]:
    hits = defaultdict(lambda: {"occurrences": 0, "lines": 0, "fps": set(), "examples": []})
    sampled = 0
    for line in lines:
        sampled += 1
        seen_in_line = set()
        for det, value in scan_line(line, detectors):
            h = hits[det.key]
            h["occurrences"] += 1
            if det.key not in seen_in_line:
                h["lines"] += 1
                seen_in_line.add(det.key)
            fp = fingerprint(value)
            masked = det.mask(value)
            if fp not in h["fps"] and masked not in h["examples"] and len(h["examples"]) < 3:
                h["examples"].append(masked)
            h["fps"].add(fp)

    by_key = {d.key: d for d in detectors}
    findings = []
    for key, h in hits.items():
        det = by_key[key]
        hit_rate = h["lines"] / sampled if sampled else 0
        per_day = hit_rate * total_lines_window / max(window_days, 1e-9)
        score, sev = risk(det, per_day, retention_days)
        findings.append({
            "stream": selector, "owner": owner,
            "detector": key, "label": det.label, "category": det.category, "gdpr_note": det.gdpr_note,
            "sampled_lines": sampled, "lines_with_hit": h["lines"], "occurrences": h["occurrences"],
            "distinct_values": len(h["fps"]), "hit_rate": round(hit_rate, 4),
            "est_lines_per_day": int(math.ceil(per_day)),
            "retention_days": retention_days, "risk_score": score, "severity": sev,
            "examples": h["examples"],
        })
    return findings


def finalize(findings: list[dict], meta: dict, streams_scanned: int, lines_sampled: int) -> dict:
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings.sort(key=lambda f: (order[f["severity"]], -f["risk_score"], f["stream"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"PII-{i:03d}"
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    return {
        "meta": {**meta, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "summary": {
            "streams_scanned": streams_scanned,
            "streams_affected": len({f["stream"] for f in findings}),
            "lines_sampled": lines_sampled,
            "findings": len(findings),
            "by_severity": counts,
            "est_pii_lines_per_day": sum(f["est_lines_per_day"] for f in findings),
        },
        "findings": findings,
    }


def window_bounds(window: str):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=parse_duration_days(window))
    return int(start.timestamp() * 1e9), int(end.timestamp() * 1e9), start, end
