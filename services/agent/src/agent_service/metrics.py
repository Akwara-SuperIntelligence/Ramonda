"""The four numbers, as Prometheus text.

Sources
    EDA §9 — run success rate, p99 turn latency, cache hit ratio, consumer lag

Delta
    No OTel exporter exists yet, so the four numbers are computed from here and
    served as text on the health server. The same queries feed a real exporter
    when one is added. Consumer lag is approximated by the age of the newest run
    event because there is no Kafka admin client in this process.
"""

from __future__ import annotations

import psycopg

from agent_service.activities import _dsn

NAMESPACE = "agent_"


def _scalar(sql: str, params: tuple = ()) -> float | int | None:
    with psycopg.connect(_dsn()) as conn:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None


def metrics_text() -> str:
    lines: list[str] = []

    # Run success rate over the last 7 days, from the run events.
    started = _scalar(
        "select count(distinct (payload::jsonb #>> '{subject,run_id}'))"
        " from outbox where id like 'run:%%:started'"
        " and created_at > now() - interval '7 days'"
    ) or 0
    failed = _scalar(
        "select count(distinct (payload::jsonb #>> '{subject,run_id}'))"
        " from outbox where id like 'run:%%:failed'"
        " and created_at > now() - interval '7 days'"
    ) or 0
    rate = (started - failed) / started if started else 0.0
    lines.append(f"# TYPE {NAMESPACE}run_success_rate gauge")
    lines.append(f"{NAMESPACE}run_success_rate {rate:.3f}")

    # p99 turn latency, from run started -> completed timestamps (7 days).
    lines.append(f"# TYPE {NAMESPACE}turn_latency_seconds gauge")
    lines.append(f"{NAMESPACE}turn_latency_seconds {_p99_latency():.3f}")

    # Cache hit ratio summed over the recent model calls.
    total = _scalar(
        "select coalesce(sum(cache_hit + cache_miss), 0) from model_calls"
        " where created_at > now() - interval '7 days'"
    ) or 0
    hits = _scalar(
        "select coalesce(sum(cache_hit), 0) from model_calls"
        " where created_at > now() - interval '7 days'"
    ) or 0
    ratio = hits / total if total else 0.0
    lines.append(f"# TYPE {NAMESPACE}cache_hit_ratio gauge")
    lines.append(f"{NAMESPACE}cache_hit_ratio {ratio:.3f}")

    # Consumer lag: age in seconds of the newest run event.
    lag = _scalar(
        "select extract(epoch from (now() - max(created_at)))"
        " from outbox where topic = 'agent.runs'"
    ) or 0.0
    lines.append(f"# TYPE {NAMESPACE}consumer_lag_seconds gauge")
    lines.append(f"{NAMESPACE}consumer_lag_seconds {lag:.1f}")

    lines.append("")
    return "\n".join(lines)


def _p99_latency() -> float:
    """p99 of (completed - started) for runs that finished in the last 7 days."""
    with psycopg.connect(_dsn()) as conn:
        cursor = conn.execute(
            "select extract(epoch from (c.created_at - s.created_at))"
            " from outbox s join outbox c"
            "   on c.payload::jsonb #>> '{subject,run_id}'"
            "      = s.payload::jsonb #>> '{subject,run_id}'"
            " where s.id like 'run:%%:started' and c.id like 'run:%%:completed'"
            " and s.created_at > now() - interval '7 days'",
        )
        rows = [r[0] for r in cursor.fetchall() if r[0] is not None]
    if not rows:
        return 0.0
    ordered = sorted(rows)
    idx = min(len(ordered) - 1, int(0.99 * len(ordered)))
    return float(ordered[idx])