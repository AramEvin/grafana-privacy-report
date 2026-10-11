"""Push fake-but-realistic logs into Loki so you can test the scanner end to end.

Every identifier is fake (example.com emails, documentation IPs, public test
card numbers), so this is safe to run anywhere.

    python lab/push_fake_logs.py --url http://localhost:3100 --lines 3000
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from privacy_report.demo import STREAMS  # noqa: E402


def labels(selector: str) -> dict:
    return dict(re.findall(r'(\w+)="([^"]*)"', selector))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3100")
    ap.add_argument("--lines", type=int, default=3000, help="lines per stream")
    ap.add_argument("--tenant", default=None)
    args = ap.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.tenant:
        headers["X-Scope-OrgID"] = args.tenant

    now = time.time_ns()
    spread = 3600 * 10**9  # spread lines over the last hour
    for sel, spec in STREAMS.items():
        step = spread // args.lines
        values = [[str(now - spread + i * step), spec["gen"]()] for i in range(args.lines)]
        for i in range(0, len(values), 1000):  # push in batches
            body = {"streams": [{"stream": labels(sel), "values": values[i:i + 1000]}]}
            r = requests.post(f"{args.url}/loki/api/v1/push", json=body, headers=headers, timeout=30)
            r.raise_for_status()
        print(f"pushed {args.lines} lines -> {sel}")


if __name__ == "__main__":
    main()
