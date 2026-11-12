#!/usr/bin/env python3
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
"""
Generates a realistic ~60k-line JSON-per-line application log covering
2026-04-22 14:00:00 → 15:00:00 UTC, with an N+1 query incident in the
checkout service starting at 14:31:18.

Deterministic (seeded) so reruns are stable. Stdlib only.
"""
import json
import random
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

OUT = Path(__file__).parent / "app.log"

START = datetime(2026, 4, 22, 14, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 4, 22, 15, 0, 0, tzinfo=timezone.utc)
DEPLOY_TS = datetime(2026, 4, 22, 14, 31, 18, tzinfo=timezone.utc)
POOL_EXHAUST_TS = datetime(2026, 4, 22, 14, 40, 0, tzinfo=timezone.utc)

SERVICES = ["checkout", "cart", "auth", "inventory"]
ENDPOINTS = {
    "checkout": ["/api/checkout/submit", "/api/checkout/summary", "/api/checkout/validate"],
    "cart": ["/api/cart", "/api/cart/add", "/api/cart/remove"],
    "auth": ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"],
    "inventory": ["/api/inventory/check", "/api/inventory/reserve"],
}
HOSTS = {svc: [f"{svc}-{i}" for i in range(1, 4)] for svc in SERVICES}


def rid(rng: random.Random) -> str:
    return "req_" + "".join(rng.choices(string.hexdigits.lower(), k=12))


def uid(rng: random.Random) -> str:
    return f"u_{rng.randint(10000, 99999)}"


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def emit(buf: list, ts: datetime, **fields) -> None:
    rec = {"ts": iso(ts)}
    rec.update(fields)
    buf.append(json.dumps(rec, separators=(",", ":")))


def healthy_request(buf: list, ts: datetime, service: str, rng: random.Random) -> None:
    """A single normal request: start + end log lines."""
    req = rid(rng)
    user = uid(rng)
    host = rng.choice(HOSTS[service])
    ep = rng.choice(ENDPOINTS[service])
    lat = rng.randint(20, 80)
    emit(buf, ts, level="INFO", service=service, host=host,
         msg=f"request_start method=POST path={ep}", request_id=req, user_id=user)
    emit(buf, ts + timedelta(milliseconds=lat), level="INFO", service=service, host=host,
         msg=f"request_end status=200 path={ep}", request_id=req, user_id=user,
         latency_ms=lat, status=200)


def post_deploy_checkout_request(buf: list, ts: datetime, rng: random.Random) -> None:
    """A checkout request after the bad deploy: N+1 queries, slow, maybe 500."""
    req = rid(rng)
    user = uid(rng)
    host = rng.choice(HOSTS["checkout"])
    ep = rng.choice(ENDPOINTS["checkout"])
    emit(buf, ts, level="INFO", service="checkout", host=host,
         msg=f"request_start method=POST path={ep}", request_id=req, user_id=user)

    mins_since = (ts - DEPLOY_TS).total_seconds() / 60.0
    n_queries = rng.randint(8, 16)
    cursor = ts
    for _ in range(n_queries):
        cursor += timedelta(milliseconds=rng.randint(2, 30))
        order_id = rng.randint(1000, 9999)
        emit(buf, cursor, level="DEBUG", service="checkout", host=host,
             msg=f'db_query sql="SELECT * FROM order_items WHERE order_id = ?" params=[{order_id}]',
             request_id=req, duration_ms=rng.randint(2, 25))

    lat = rng.randint(800, 4000) + int(mins_since * 50)

    # After pool exhaustion, some requests fail outright
    pool_down = ts >= POOL_EXHAUST_TS
    if pool_down and rng.random() < 0.35:
        emit(buf, cursor + timedelta(milliseconds=5), level="ERROR", service="checkout", host=host,
             msg="DB connection pool exhausted (active=50/50, waiters=12)",
             request_id=req)
        emit(buf, cursor + timedelta(milliseconds=8), level="ERROR", service="checkout", host=host,
             msg=f"request_end status=500 path={ep} error=PoolTimeout",
             request_id=req, user_id=user, latency_ms=lat, status=500)
    else:
        if pool_down and rng.random() < 0.5:
            emit(buf, cursor, level="WARN", service="checkout", host=host,
                 msg=f"db_pool high utilization active={rng.randint(42, 50)}/50",
                 request_id=req)
        emit(buf, cursor + timedelta(milliseconds=10), level="INFO", service="checkout", host=host,
             msg=f"request_end status=200 path={ep}", request_id=req, user_id=user,
             latency_ms=lat, status=200)


def auth_red_herring(buf: list, rng: random.Random) -> None:
    """Unrelated auth ERRORs around 14:15 that self-resolve — a red herring."""
    base = START + timedelta(minutes=15)
    for i in range(6):
        ts = base + timedelta(seconds=i * 7 + rng.randint(0, 3))
        emit(buf, ts, level="ERROR", service="auth", host=rng.choice(HOSTS["auth"]),
             msg="upstream identity-provider timeout after 5000ms", request_id=rid(rng),
             upstream="idp.internal")
    emit(buf, base + timedelta(seconds=55), level="WARN", service="auth",
         host="auth-1", msg="circuit_breaker OPEN for idp.internal (will retry in 30s)")
    emit(buf, base + timedelta(seconds=90), level="INFO", service="auth",
         host="auth-1", msg="circuit_breaker CLOSED for idp.internal — recovered")


def background_noise(buf: list, rng: random.Random) -> None:
    """Healthchecks, GC pauses, cache misses — realistic chatter."""
    t = START
    while t < END:
        for svc in SERVICES:
            emit(buf, t, level="DEBUG", service=svc, host=rng.choice(HOSTS[svc]),
                 msg="healthcheck OK", uptime_s=rng.randint(3600, 86400))
        t += timedelta(seconds=10)

    for _ in range(40):
        ts = START + timedelta(seconds=rng.randint(0, 3600))
        svc = rng.choice(SERVICES)
        emit(buf, ts, level="WARN", service=svc, host=rng.choice(HOSTS[svc]),
             msg=f"GC pause {rng.randint(80, 350)}ms (G1 young gen)")

    for _ in range(120):
        ts = START + timedelta(seconds=rng.randint(0, 3600))
        emit(buf, ts, level="DEBUG", service="inventory", host=rng.choice(HOSTS["inventory"]),
             msg=f"cache_miss key=sku:{rng.randint(100000, 999999)}")

    emit(buf, DEPLOY_TS, level="INFO", service="checkout", host="checkout-1",
         msg="deploy_complete version=a3f9c21 strategy=rolling", commit="a3f9c21")


def main() -> None:
    rng = random.Random(42)
    buf: list[str] = []

    # Baseline traffic across the full hour, ~12 req/s split across services.
    # After deploy, checkout requests go through the degraded path.
    t = START
    while t < END:
        n = rng.randint(4, 6)
        for _ in range(n):
            jitter = timedelta(milliseconds=rng.randint(0, 999))
            ts = t + jitter
            svc = rng.choices(SERVICES, weights=[3, 3, 2, 2])[0]
            if svc == "checkout" and ts >= DEPLOY_TS:
                post_deploy_checkout_request(buf, ts, rng)
            else:
                healthy_request(buf, ts, svc, rng)
        t += timedelta(seconds=1)

    auth_red_herring(buf, rng)
    background_noise(buf, rng)

    # Sort chronologically (cheap parse of fixed-width ISO prefix)
    buf.sort(key=lambda line: line[7:31])

    with TemporaryDirectory(prefix=f".{OUT.name}.", dir=OUT.parent) as temp_dir:
        staged = Path(temp_dir) / OUT.name
        staged.write_text("\n".join(buf) + "\n", encoding="utf-8")
        staged.replace(OUT)
    print(f"wrote {OUT} — {len(buf):,} lines, {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
