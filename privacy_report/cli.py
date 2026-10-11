"""CLI: `scan` (live Loki), `demo` (synthetic data), `render` (findings.json -> DOCX)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import yaml

from . import __version__
from .detectors import get_detectors
from .scanner import analyse_stream, finalize, parse_duration_days, window_bounds


def _retention_for(selector: str, cfg: dict) -> float:
    for o in cfg.get("retention_overrides", []):
        if all(part.strip() in selector for part in o["match"].strip("{}").split(",")):
            return parse_duration_days(o["period"])
    return parse_duration_days(cfg.get("default_retention", "31d"))


def _owner_for(labels_or_selector, cfg: dict) -> str:
    for o in cfg.get("owners", []):
        if all(part.strip() in labels_or_selector for part in o["match"].strip("{}").split(",")):
            return o["owner"]
    return ""


def cmd_scan(args):
    from .loki import LokiClient, selector_from_labels

    cfg = yaml.safe_load(open(args.config))
    lk, sc, rp = cfg["loki"], cfg["scan"], cfg.get("report", {})
    client = LokiClient(lk["url"], lk.get("tenant"), os.getenv(lk.get("user_env", ""), lk.get("user")),
                        os.getenv(lk.get("token_env", "LOKI_TOKEN")), verify_tls=lk.get("verify_tls", True))
    detectors = get_detectors(sc.get("detectors"))
    start_ns, end_ns, start, end = window_bounds(sc.get("window", "24h"))
    window_days = parse_duration_days(sc.get("window", "24h"))
    group_by = sc.get("group_by", ["namespace", "app"])

    streams = set()
    for sel in sc["selectors"]:
        for labels in client.series(sel, start_ns, end_ns):
            streams.add(selector_from_labels(labels, group_by))
    streams = sorted(s for s in streams if s != "{}")
    print(f"discovered {len(streams)} streams", file=sys.stderr)

    findings, sampled_total = [], 0
    for sel in streams:
        lines = list(client.sample(sel, start_ns, end_ns, sc.get("sample_lines_per_stream", 5000)))
        total = client.count_lines(sel, sc.get("window", "24h"))
        sampled_total += len(lines)
        f = analyse_stream(sel, lines, total, window_days, detectors, _retention_for(sel, sc), _owner_for(sel, sc))
        print(f"  {sel}: {len(lines)} lines, {len(f)} findings", file=sys.stderr)
        findings += f

    meta = _meta(rp, sc, lk["url"], start, end, [d.key for d in detectors])
    data = finalize(findings, meta, len(streams), sampled_total)
    _write(data, args)


def cmd_demo(args):
    from .demo import STREAMS, stream_lines

    detectors = get_detectors(None)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    findings, sampled = [], 0
    for sel, spec in STREAMS.items():
        lines = stream_lines(sel, args.sample)
        sampled += len(lines)
        findings += analyse_stream(sel, lines, spec["total_per_day"], 1, detectors,
                                   parse_duration_days(spec["retention"]), spec["owner"])
    rp = {"title": "Telemetry Privacy Report", "organization": "Example Corp (demo data)",
          "environment": "production", "author": "Observability Guild — grafana-privacy-report",
          "scope": "All production namespaces ingested by Loki (synthetic demo dataset)"}
    sc = {"selectors": ['{namespace=~".+"}'], "group_by": ["namespace", "app"], "window": "24h",
          "sample_lines_per_stream": args.sample}
    meta = _meta(rp, sc, "http://loki-gateway.monitoring:3100 (demo)", start, end, [d.key for d in detectors])
    _write(finalize(findings, meta, len(STREAMS), sampled), args)


def cmd_render(args):
    from .render_docx import render
    data = json.load(open(args.findings))
    print(render(data, args.out))


def _meta(rp, sc, source, start, end, detector_keys):
    return {
        "title": rp.get("title", "Telemetry Privacy Report"),
        "subtitle": rp.get("subtitle", "Personal data & secrets discovered in log pipelines — DPIA annex"),
        "organization": rp.get("organization", ""), "environment": rp.get("environment", ""),
        "author": rp.get("author", ""), "scope": rp.get("scope", ""), "version": rp.get("version", "1.0"),
        "classification": rp.get("classification", "CONFIDENTIAL — contains masked personal data findings"),
        "source": source, "selectors": sc["selectors"], "group_by": sc.get("group_by", []),
        "window": sc.get("window", "24h"), "sample_lines": sc.get("sample_lines_per_stream", 5000),
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "detectors": detector_keys, "tool_version": __version__,
    }


def _write(data, args):
    with open(args.json, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"wrote {args.json}", file=sys.stderr)
    if args.out:
        from .render_docx import render
        print(render(data, args.out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="grafana-privacy-report", description=__doc__)
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("scan", help="scan a live Loki")
    s.add_argument("-c", "--config", default="config.yaml")
    s.add_argument("--json", default="findings.json")
    s.add_argument("-o", "--out", default="privacy-report.docx")
    s.set_defaults(fn=cmd_scan)
    d = sub.add_parser("demo", help="generate a report from synthetic data")
    d.add_argument("--sample", type=int, default=5000)
    d.add_argument("--json", default="findings.json")
    d.add_argument("-o", "--out", default="privacy-report-demo.docx")
    d.set_defaults(fn=cmd_demo)
    r = sub.add_parser("render", help="render an existing findings.json")
    r.add_argument("findings")
    r.add_argument("-o", "--out", default="privacy-report.docx")
    r.set_defaults(fn=cmd_render)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
