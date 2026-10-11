# grafana-privacy-report

**Find personal data and secrets hiding in your Loki logs — and get a DPIA-ready Word report with copy-paste fixes.**

Logs are the biggest unmanaged copy of personal data in most companies. Emails in access logs, card numbers in
error messages, JWTs in debug output. Everyone with access to the Loki data source can query them, for as long as
retention allows. This tool turns that hidden risk into a document your **DPO, security team and platform team**
can all act on.

| What you get | For whom |
| --- | --- |
| Findings register with risk scores (weight × volume × retention) | Security, DPO |
| Data inventory per stream with *purpose / lawful basis* columns to fill in | DPO (DPIA annex) |
| Generated **Grafana Alloy** `loki.process` config, scoped per affected stream | Platform team |
| Generated **OpenTelemetry Collector** `transform` processor | Platform team |
| LogQL verification queries, Loki delete requests, per-stream retention config | SRE |
| `findings.json` for CI gates, dashboards or ticketing | Automation |

See [`examples/Telemetry-Privacy-Report-SAMPLE.docx`](examples/) for a full report generated from synthetic data.

## Quick start

```bash
pip install .
grafana-privacy-report demo                      # no Loki needed: synthetic data -> privacy-report-demo.docx

cp config.example.yaml config.yaml               # point it at your Loki
export LOKI_TOKEN=...                            # logs:read is enough
grafana-privacy-report scan -c config.yaml       # -> findings.json + privacy-report.docx
grafana-privacy-report render findings.json -o report.docx   # re-render without re-scanning
```

## Try it in 10 minutes

`lab/` contains Docker Compose with Loki, Grafana, Alloy and fake leaky logs. You can see the leak, run the scan,
apply the generated Alloy fix and re-scan to 0 findings. Step-by-step: [TESTING.md](TESTING.md).

## Privacy by design

The scanner itself must not become a leak:

- **Read-only** — only `series`, `query_range` and instant `query` calls; nothing is written to Loki.
- **Masked at scan time** — raw values never leave the process; reports contain `a***@e***.com`, `••••1111`.
- **Fingerprints, not values** — distinct values are counted with truncated SHA-256 hashes.
- **Validated detectors** — Luhn for cards, mod-97 for IBANs, public-range check for IPs, to keep false positives low.

## Detectors

`email` · `card` · `iban` · `jwt` · `bearer` · `aws_key` · `phone` (E.164) · `ip` (public only).
Add one by appending a `Detector` in `privacy_report/detectors.py`: regex, optional validator, mask function,
category, weight, and an RE2-compatible `redact_regex` (non-capturing groups only) used for the generated fixes.

## Limitations

Pattern matching cannot find names, postal addresses or free-text health data, and misses values that are
base64-encoded or split across lines. A clean report means "none of the listed patterns found in the sample",
not "this stream has no personal data". The report is an input to a DPIA, not legal advice.

## Automate it

`.github/workflows/monthly-privacy-report.yml` runs the scan monthly, uploads the DOCX, and fails if any
Critical finding appears — a simple privacy gate for your log pipeline.

## Roadmap / good first issues

- [ ] Tempo support: scan span attributes via TraceQL (`{ span.http.url =~ ".*email=.*" }`)
- [ ] Allowlist per stream/field to silence accepted findings
- [ ] Push findings as Grafana annotations and ship a companion dashboard
- [ ] More detectors: national ID formats (per country), GitHub/Slack tokens, MAC addresses
- [ ] Localized report templates (DE, FR, ES, HY)

## License

Apache-2.0. Community project; not an official Grafana Labs publication. Grafana and Loki are trademarks of Grafana Labs.
