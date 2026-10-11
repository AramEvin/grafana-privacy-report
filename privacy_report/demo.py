"""Synthetic, obviously-fake log streams so anyone can try the report without a Loki instance.

All identifiers are fake: example.* domains, RFC 5737 documentation IPs,
public test card numbers, the ECBS sample IBAN and AWS's documented example key.
"""
from __future__ import annotations

import random

random.seed(42)

NAMES = ["anna", "davit", "lena", "omar", "sofia", "mark", "aram", "julia", "nina", "tom"]
DOC_IPS = [f"203.0.113.{i}" for i in range(1, 60)] + [f"198.51.100.{i}" for i in range(1, 40)]
TEST_CARDS = ["4111111111111111", "5555555555554444", "4012888888881881", "378282246310005"]
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTQyIiwicm9sZSI6ImFkbWluIn0.dGVzdC1zaWduYXR1cmUtZmFrZQ"


def email():
    return f"{random.choice(NAMES)}.{random.randint(1, 999)}@example.com"


def ip():
    return random.choice(DOC_IPS)


STREAMS = {
    '{namespace="payments", app="checkout-api"}': {
        "owner": "Payments team", "retention": "90d", "total_per_day": 1_850_000,
        "gen": lambda: random.choice([
            lambda: f'level=info msg="order created" order_id={random.randint(10**6, 10**7)} customer={email()} client_ip={ip()}',
            lambda: f'level=error msg="charge failed" card={random.choice(TEST_CARDS)} reason=do_not_honor',
            lambda: f'level=debug msg="payload" body={{"email":"{email()}","iban":"DE89 3704 0044 0532 0130 00"}}',
            lambda: 'level=info msg="healthcheck ok" latency_ms=3',
            lambda: 'level=info msg="healthcheck ok" latency_ms=4',
            lambda: f'level=info msg="cart updated" items={random.randint(1, 9)}',
        ])(),
    },
    '{namespace="identity", app="auth-service"}': {
        "owner": "Identity team", "retention": "30d", "total_per_day": 640_000,
        "gen": lambda: random.choice([
            lambda: f'level=info msg="login success" user={email()} ip={ip()}',
            lambda: f'level=warn msg="token refresh" Authorization: Bearer {JWT}',
            lambda: f'level=info msg="mfa sms sent" phone=+3749{random.randint(1000000, 9999999)}',
            lambda: 'level=info msg="session validated" ttl=3600',
            lambda: 'level=info msg="session validated" ttl=3600',
        ])(),
    },
    '{namespace="ingress", app="nginx-ingress"}': {
        "owner": "Platform team", "retention": "31d", "total_per_day": 9_400_000,
        "gen": lambda: f'{ip()} - - "GET /api/v1/products?page={random.randint(1, 40)} HTTP/1.1" 200 {random.randint(200, 9000)}'
        if random.random() < 0.97 else
        f'{ip()} - - "GET /reset?email={email()} HTTP/1.1" 302 0',
    },
    '{namespace="support", app="helpdesk-bot"}': {
        "owner": "Customer Support", "retention": "180d", "total_per_day": 42_000,
        "gen": lambda: random.choice([
            lambda: f'level=info msg="ticket opened" from={email()} phone=+4479{random.randint(10000000, 99999999)}',
            lambda: 'level=info msg="intent classified" intent=billing confidence=0.91',
        ])(),
    },
    '{namespace="data", app="billing-export"}': {
        "owner": "Data Engineering", "retention": "14d", "total_per_day": 12_000,
        "gen": lambda: random.choice([
            lambda: 'level=info msg="s3 upload" key_id=AKIAIOSFODNN7EXAMPLE bucket=billing-exports',
            lambda: 'level=info msg="export finished" rows=18233',
            lambda: 'level=info msg="export finished" rows=17950',
            lambda: 'level=info msg="export finished" rows=18102',
        ])(),
    },
    '{namespace="catalog", app="search-api"}': {
        "owner": "Catalog team", "retention": "31d", "total_per_day": 2_100_000,
        "gen": lambda: f'level=info msg="query" q="running shoes" took_ms={random.randint(4, 80)} upstream=10.12.{random.randint(0, 9)}.{random.randint(1, 250)}',
    },
}


def stream_lines(selector: str, n: int):
    gen = STREAMS[selector]["gen"]
    return [gen() for _ in range(n)]
