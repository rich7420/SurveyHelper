"""OPTIONAL read-only analytics over the Postgres store, via DuckDB (Phase 8 eval).

Install with the `analytics` extra: `uv sync --extra analytics`. NOT required by the
core system — cross-testing showed DuckDB is premature as a live dashboard (slower
than direct Postgres at our scale + a runtime extension fetch). Its real value here
is the golden-set eval: DuckDB reads a CSV/parquet and joins it against Postgres in
one query, which plain Postgres can't do. Operational truth always stays in Postgres.
"""

from __future__ import annotations

import re

import duckdb

from . import config


def _connect() -> duckdb.DuckDBPyConnection:
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+):(\d+)/(\w+)", config.DSN)
    if not m:
        raise ValueError(f"unparseable DSN: {config.DSN}")
    user, pw, host, port, db = m.groups()
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH 'host={host} port={port} dbname={db} user={user} password={pw}' "
                f"AS pg (TYPE postgres, READ_ONLY)")
    return con


def cost_by_day() -> list[tuple]:
    con = _connect()
    return con.execute(
        """SELECT CAST("at" AS DATE) AS day, count(*) AS calls,
                  sum(tokens) AS tokens, round(sum(cost_usd), 3) AS cost_usd
           FROM pg.public.usage_log GROUP BY 1 ORDER BY 1""").fetchall()


def cost_by_job_type() -> list[tuple]:
    """OLAP join across Postgres tables — cost attributed to each kind of work."""
    con = _connect()
    return con.execute(
        """SELECT coalesce(j.type, 'other') AS job_type, count(*) AS calls,
                  round(sum(u.cost_usd), 3) AS cost_usd
           FROM pg.public.usage_log u
           LEFT JOIN pg.public.research_jobs j ON j.id = u.job_id
           GROUP BY 1 ORDER BY cost_usd DESC""").fetchall()


def coverage_funnel() -> dict:
    con = _connect()
    papers, citations = con.execute(
        "SELECT (SELECT count(*) FROM pg.public.papers), "
        "(SELECT count(*) FROM pg.public.citations)").fetchone()
    cards, tldr, deep = con.execute(
        """SELECT count(*),
                  sum(CASE WHEN json_extract_string(CAST(step_status AS VARCHAR),'$.\"1\"')='ok' THEN 1 ELSE 0 END),
                  sum(CASE WHEN json_extract_string(CAST(step_status AS VARCHAR),'$.\"2\"')='ok' THEN 1 ELSE 0 END)
           FROM pg.public.paper_analysis""").fetchone()
    return {"papers": papers, "citations": citations, "cards": cards,
            "with_tldr": int(tldr or 0), "deep_analyzed": int(deep or 0)}


def report() -> str:
    lines = ["surveyHelper analytics (DuckDB over Postgres)", "=" * 46]
    f = coverage_funnel()
    lines.append(f"coverage: {f['papers']} papers, {f['citations']} edges -> "
                 f"{f['cards']} cards -> {f['with_tldr']} tldr -> {f['deep_analyzed']} deep")
    lines.append("\ncost by job type:")
    for jt, calls, cost in cost_by_job_type():
        lines.append(f"  {jt:<14} {calls:>4} calls  ${cost}")
    lines.append("\ncost by day:")
    for day, calls, tokens, cost in cost_by_day():
        lines.append(f"  {day}  {calls:>4} calls  {tokens:>8} tok  ${cost}")
    return "\n".join(lines)


def main() -> None:
    print(report())


if __name__ == "__main__":
    main()
