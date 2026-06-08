# Decision: event streaming (Kafka/Redpanda) — not yet

_Extends plan.md §18. Status: **decided — stay on the Postgres queue for now.**_

## Question
Do we need an event-streaming backbone (Kafka/Redpanda) for the async background work,
or does the Postgres job queue suffice?

## Current design
- `research_jobs` is the queue, drained with `FOR UPDATE SKIP LOCKED`.
- `notifications` is the outbox the OpenClaw heartbeat reads.
- Jobs carry `run_after`/`attempts` (deferred retry) and a `job_papers` frontier (resumable BFS).

This **already is** the async/event pattern: durable, at-least-once, resumable, retryable.

## Why streaming is NOT justified now
1. **Single local user, modest volume.** A streaming bus is operational weight (another service,
   partitions, offsets) with no payoff at this scale.
2. **Parallel workers already work without it.** `FOR UPDATE SKIP LOCKED` lets *N* worker processes
   pull from the same queue safely. Phase-4 BFS fan-out can add workers with zero new infra.
3. **One consumer.** Only OpenClaw consumes notifications, on its heartbeat cadence (~30 min/1 h).
   Streaming shines with *many* independent consumers — we have one.
4. **Replay/audit is covered.** `research_jobs` history + `usage_log` + per-step status give the audit
   trail; we don't need a replayable log yet.

## If near-real-time push is wanted before Kafka is justified
Use **Postgres `LISTEN`/`NOTIFY`** — built-in pub/sub, zero new infrastructure. The worker `NOTIFY`s
on completion; a consumer `LISTEN`s for sub-second delivery instead of polling. This is the cheap
incremental step and keeps everything in the one datastore.

## Concrete triggers to revisit (adopt Redpanda/Kafka when ANY is true)
- A **second consumer** appears that needs the stream independently (e.g. a live graph-viz UI updating
  as `edge.found` events arrive).
- Workers go **distributed / cross-machine** (the DB queue is fine on one host; a bus is cleaner across hosts).
- We need **event replay / audit** at a scale Postgres history can't serve comfortably.

## Keep the future swap cheap
Name the worker's domain events now and emit them through one small helper, even though they currently
land in `notifications`/logs: `paper.discovered`, `paper.analyzed`, `edge.found`, `synthesis.ready`
(plan §18). When a real bus is introduced, only that helper changes.
