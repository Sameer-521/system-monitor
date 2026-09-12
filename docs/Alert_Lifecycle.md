# Alert Lifecycle

## Overview

Every poller tick, `fetch_system_resources()` builds a snapshot and passes it through
`AlertRegistry.evaluate()` (app/engine/pipeline.py). The registry fans the snapshot out to
each registered evaluator, collects the `Alert` objects they emit, and runs them through
`manage()` (app/alerts/registry.py), which classifies each alert against the stored alert
for the same `metric` key and decides what gets published. Published alerts land in the
snapshot's `alerts` key and stream to SSE clients.

Evaluators own their detection and lifecycle decisions (hysteresis windows, state
machines); the registry owns deduplication, escalation bookkeeping, resolution, and
cooldown. Evaluators can emit on every tick without spamming — the manager collapses
duplicates.

## Flow

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                               EVALUATION LAYER                                │
│                                                                               │
│         fetch_system_resources() ──► AlertRegistry.evaluate(snapshot)         │
│                                       │                                       │
│             ┌─────────────────────────┬─────────────────────────┐             │
│             ▼                         ▼                         ▼             │
│    ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│    │ CpuAnomalyAlert │       │   HighLoadAvg   │       │  HighCpuUsage   │    │
│    │ z-score vs      │       │ N-of-M tick     │       │ N-of-M bucket   │    │
│    │ baseline        │       │ windows (1m/5m) │       │ windows (70/90) │    │
│    │ cpu_anomaly     │       │ load_average    │       │ cpu_usage       │    │
│    └────────┬────────┘       └────────┬────────┘       └────────┬────────┘    │
│             │                         │                         │             │
│             └─────────────────────────┼─────────────────────────┘             │
│                                       ▼                                       │
│          list[Alert]  (FIRING / RESOLVED, severity, message, extra)           │
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                                 MANAGER LAYER                                 │
│                                                                               │
│    AlertRegistry.manage(alerts) — classify each incoming alert                │
│    per metric: {"content": Alert, "cooldown_till": fired_at + cooldown}       │
│                                                                               │
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        ▼
                snapshot["alerts"] ──► broadcaster ──► SSE clients
```

## Alert Model

`app/models/alert.py`:

| field      | notes                                                          |
| ---------- | -------------------------------------------------------------- |
| `metric`   | storage/fan-out key: `cpu_anomaly`, `load_average`, `cpu_usage` |
| `severity` | `INFO / DEBUG / WARNING / CRITICAL`                             |
| `state`    | `OK / FIRING / RESOLVED` — resolved alerts carry severity INFO  |
| `message`  | human-readable, includes observed values and thresholds         |
| `fired_at` | `time.monotonic()` at emission; drives cooldown                 |
| `extra`    | free-form: observed values, thresholds, triggering window       |

## Manager Classification

`AlertRegistry.manage()` — per alert, against the stored alert for the same metric:

| stored    | incoming                      | action                                       |
| --------- | ----------------------------- | -------------------------------------------- |
| none      | any                           | store + publish (fire)                       |
| `FIRING`  | same severity                 | drop (dedupe)                                |
| `FIRING`  | different severity            | store + publish (escalate / de-escalate)     |
| `FIRING`  | `RESOLVED`                    | store `RESOLVED` + cooldown, publish (resolve) |
| `RESOLVED`| any, cooldown active          | drop (flap guard)                            |
| `RESOLVED`| any, cooldown expired         | store + publish (refire)                     |

## Cooldown

`cooldown = 60s`, tracked per metric as `cooldown_till = fired_at + cooldown`. A metric
that just resolved cannot refire until the cooldown expires — this suppresses flapping
when a value oscillates around a threshold boundary.
