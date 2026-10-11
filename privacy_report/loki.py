"""Minimal, read-only Loki HTTP client (works with Loki OSS, GEL and Grafana Cloud Logs)."""
from __future__ import annotations

import time
from typing import Iterator

import requests


class LokiClient:
    def __init__(self, url: str, tenant: str | None = None, user: str | None = None,
                 token: str | None = None, timeout: int = 60, verify_tls: bool = True):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.s.verify = verify_tls
        self.timeout = timeout
        if tenant:
            self.s.headers["X-Scope-OrgID"] = tenant
        if user and token:                      # Grafana Cloud: instance ID + access-policy token
            self.s.auth = (user, token)
        elif token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, params: dict) -> dict:
        r = self.s.get(f"{self.url}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def series(self, selector: str, start_ns: int, end_ns: int) -> list[dict]:
        """Distinct label sets matching a selector -> one entry per stream."""
        data = self._get("/loki/api/v1/series", {"match[]": selector, "start": start_ns, "end": end_ns})
        return data.get("data", [])

    def sample(self, selector: str, start_ns: int, end_ns: int, limit: int) -> Iterator[str]:
        """Yield up to `limit` raw log lines, newest first (read-only query_range)."""
        data = self._get("/loki/api/v1/query_range", {
            "query": selector, "start": start_ns, "end": end_ns,
            "limit": limit, "direction": "backward",
        })
        for stream in data.get("data", {}).get("result", []):
            for _ts, line in stream.get("values", []):
                yield line

    def count_lines(self, selector: str, window: str) -> int:
        """Total lines for the stream in the window (used to extrapolate sample hit-rates)."""
        q = f"sum(count_over_time({selector}[{window}]))"
        data = self._get("/loki/api/v1/query", {"query": q, "time": time.time_ns()})
        res = data.get("data", {}).get("result", [])
        return int(float(res[0]["value"][1])) if res else 0


def selector_from_labels(labels: dict, keys: list[str]) -> str:
    parts = [f'{k}="{labels[k]}"' for k in keys if k in labels]
    return "{" + ", ".join(parts) + "}"
