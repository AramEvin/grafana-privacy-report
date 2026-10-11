# Testing guide

Two ways to test: a **local lab** (safe, fake data, 10 minutes) and your **real Loki** (read-only).

## What you need

| Tool | Why | Check |
| --- | --- | --- |
| Docker Desktop (or Docker Engine + Compose v2) | Runs Loki, Grafana, Alloy | `docker compose version` |
| Python 3.10+ | Runs the scanner | `python --version` |
| ~2 GB free RAM, ports 3000 / 3100 / 3500 / 12345 free | Lab containers | — |

No accounts, no internet services, no real personal data. All "PII" in the lab is fake
(example.com emails, documentation IP ranges, public test card numbers).

## Part 1 — Local lab

### 1. Install the scanner

```bash
unzip grafana-privacy-report.zip && cd grafana-privacy-report
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install .
```

### 2. Start the lab

```bash
cd lab
docker compose up -d
docker compose logs -f seed        # wait for "SEED DONE", then Ctrl+C
cd ..
```

This starts Loki, Grafana and Alloy, then sends the same leaky logs twice:
straight into Loki (**before**), and through Alloy's generated redaction (**after**, label `pipeline="alloy"`).

### 3. See the leak yourself

Open http://localhost:3000 → **Explore** → Loki, and run:

```logql
{namespace="payments"}
```

You will see emails, card numbers and IPs in plain text. Now run:

```logql
{pipeline="alloy", namespace="payments"}
```

Same logs, but with `<redacted:email>`, `<redacted:card>` and so on.

### 4. Generate the "before" report

```bash
grafana-privacy-report scan -c lab/config.lab.yaml -o report-before.docx --json findings-before.json
```

Expected: 6 streams scanned, 5 affected, 13 findings (3 Critical). `search-api` shows 0 findings
because it only logs private IPs, which proves the detectors don't over-report.

### 5. Prove the fix works

```bash
grafana-privacy-report scan -c lab/config.lab-after.yaml -o report-after.docx --json findings-after.json
```

Expected: **0 findings** on every stream. Before = 13, after = 0 is the screenshot for your blog post.

### 6. Clean up

```bash
cd lab && docker compose down
```

## Part 2 — Your real Loki (or Grafana Cloud)

The scanner is read-only, so it is safe on production, but agree with your security team first:
it reads log content, and the report contains masked findings.

1. `cp config.example.yaml config.yaml`
2. Set `loki.url`:
   - Self-hosted: `http://<loki-gateway>:3100`; add `tenant:` if multi-tenant (`X-Scope-OrgID`).
   - Grafana Cloud: the Loki URL from *My Account → Loki → Details*; set `LOKI_USER` (instance ID)
     and `LOKI_TOKEN` (access-policy token with only `logs:read`).
3. Start small: one namespace, `window: 1h`, `sample_lines_per_stream: 1000`.
4. Copy your real retention and stream owners into `retention_overrides` and `owners`.
5. Run `grafana-privacy-report scan -c config.yaml`.

Test the generated Alloy config in a staging pipeline first, then compare before/after exactly
as in Part 1.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Connection refused` on 3100 | Loki takes ~15 s to start: `docker compose logs loki` |
| `discovered 0 streams` | Seed not finished, or `window` too short for the data's age |
| `401` / `403` | Wrong token or missing tenant; Grafana Cloud needs user **and** token |
| `max entries limit` error | Lower `sample_lines_per_stream` (default Loki limit is 5000) |
| Port already in use | Change the left side of `ports:` in `docker-compose.yml` |
