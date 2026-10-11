"""Turn findings into copy-paste fixes: Alloy, OTel Collector, Loki retention/delete, LogQL checks."""
from __future__ import annotations

from collections import defaultdict

from .detectors import BY_KEY


def _alloy_str(s: str) -> str:
    # Alloy raw string (backticks): no escaping needed, regexes stay readable
    if "`" not in s:
        return "`" + s + "`"
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ottl_yaml(s: str) -> str:
    # OTTL string literal inside a single-quoted YAML scalar
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "''")


def alloy_config(findings: list[dict]) -> str:
    per_stream = defaultdict(list)
    for f in findings:
        if f["detector"] not in per_stream[f["stream"]]:
            per_stream[f["stream"]].append(f["detector"])
    out = ['loki.process "redact_pii" {', "  forward_to = [loki.write.default.receiver]", ""]
    for stream, keys in per_stream.items():
        out.append(f"  // {stream}")
        out.append("  stage.match {")
        out.append(f"    selector = {_alloy_str(stream)}")
        for k in keys:
            d = BY_KEY[k]
            out += ["    stage.replace {",
                    f"      expression = {_alloy_str('(' + d.redact_regex + ')')}",
                    f"      replace    = \"<redacted:{k}>\"",
                    "    }"]
        out.append("  }")
        out.append("")
    out.append("}")
    return "\n".join(out)


def otel_config(findings: list[dict]) -> str:
    keys = sorted({f["detector"] for f in findings}, key=lambda k: list(BY_KEY).index(k))
    out = ["processors:", "  transform/redact_pii:", "    error_mode: ignore", "    log_statements:",
           "      - context: log", "        statements:"]
    for k in keys:
        out.append(f"          - 'replace_pattern(body, \"{_ottl_yaml(BY_KEY[k].redact_regex)}\", \"<redacted:{k}>\")'")
    out.append("# add transform/redact_pii to service.pipelines.logs.processors (before the exporter)")
    return "\n".join(out)


def logql_check(f: dict) -> str:
    rx = BY_KEY[f["detector"]].redact_regex
    return f"sum(count_over_time({f['stream']} |~ `{rx}` [1h]))"


def delete_request(f: dict, start_iso: str, end_iso: str) -> str:
    rx = BY_KEY[f["detector"]].redact_regex
    q = f"{f['stream']} |~ `{rx}`"
    return ("curl -G -X POST \"$LOKI_URL/loki/api/v1/delete\" \\\n"
            "  -H \"X-Scope-OrgID: $TENANT\" \\\n"
            f"  --data-urlencode 'query={q}' \\\n"
            f"  --data-urlencode 'start={start_iso}' \\\n"
            f"  --data-urlencode 'end={end_iso}'")


def retention_config(findings: list[dict], target_days: int = 7) -> str:
    streams = sorted({f["stream"] for f in findings if f["severity"] in ("Critical", "High")})
    out = ["limits_config:", "  retention_period: 744h        # tenant default (example)",
           "  deletion_mode: filter-and-delete", "  retention_stream:"]
    for i, s in enumerate(streams, 1):
        out += [f"    - selector: '{s}'", f"      priority: {i}", f"      period: {target_days * 24}h"]
    out += ["compactor:", "  retention_enabled: true", "  delete_request_store: filesystem   # match your object store"]
    return "\n".join(out)
