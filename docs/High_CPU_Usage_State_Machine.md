# High CPU Usage State Machine Specification

This document defines the static thresholds, hysteresis rules, and bucket counts for monitoring CPU usage percentage.

---

## State Transition Diagram

```
                                 (2) avg >= 90%, 3/4b (bypasses WARNING)
       +--------------------------------------------->----------------------------------------------+
       |                                                                                            v
  +----|-----+------(1) avg >= 70%, 5/6b------->+----------+------(3) avg >= 90%, 3/4b------->+----------+
  |    OK    |                                  | WARNING  |                                  | CRITICAL |
  +----------+                                  +----------+                                  +----------+
   ^ ^                                            |    ^                                        |     |
   | |                                            |    |                                        |     |
   | +<-------(4) avg < 70%, 6/8b-----------------+    +<--------(5) avg < 90%, 5/6b------------+     |
   |                                                                                                  |
   +<----------(6) avg < 70%, crit 5/6b AND warn 6/8b in same pass------------------------------------+

(1) OK --> WARNING        usage >= 70%   5 of 6 buckets
(2) OK --> CRITICAL       usage >= 90%   3 of 4 buckets (bypasses WARNING entirely)
(3) WARNING --> CRITICAL  usage >= 90%   3 of 4 buckets
(4) WARNING --> OK        usage < 70%    6 of 8 buckets
(5) CRITICAL --> WARNING  usage < 90%    5 of 6 buckets (warn recovery not met yet)
(6) CRITICAL --> OK       usage < 70%    crit recovery 5/6 AND warn recovery 6/8 in the same pass
(7) WARNING --> WARNING   usage >= 70%   recovery tick = false
(8) CRITICAL --> CRITICAL usage >= 90%   recovery tick = false
```

- `usage` = bucket average of `cpu.usage_percentage`; one bucket = 10 samples = 10 seconds.
- `N/Mb` = N breach buckets within a sliding window of M buckets.

## Sliding Windows

| window                     | N of M | condition              |
| -------------------------- | ------ | ---------------------- |
| `critical_ticks`           | 3 / 4  | bucket avg >= 90       |
| `warning_ticks`            | 5 / 6  | bucket avg >= 70       |
| `critical_recovery_ticks`  | 5 / 6  | state = CRITICAL, avg < 90 |
| `warning_recovery_ticks`   | 6 / 8  | state != OK, avg < 70  |

- Window appends are gated by the **current** state, not the checked transition:
  `warning_recovery` keeps accumulating while CRITICAL (state != OK), which is
  what allows (6) — both recovery windows fill in parallel below 70%.
- All four windows are cleared on entry to a new state; (5) deliberately keeps
  `warning_recovery_ticks` so the resolve can complete on the next bucket.

## Per-Bucket Evaluation

Checks run in priority order on every bucket flush:

1. critical trigger — `critical_ticks >= 3` and state != CRITICAL
2. critical recovery — `critical_recovery_ticks >= 5` and state = CRITICAL,
   then escalate-to-OK if `warning_recovery_ticks >= 6`, else de-escalate
3. warning trigger — `warning_ticks >= 5` and state = OK
4. warning recovery — `warning_recovery_ticks >= 6` and state = WARNING

## Alert Emissions

| transition             | severity | state    |
| ---------------------- | -------- | -------- |
| (1) (3) warning firing | WARNING  | FIRING   |
| (2) (3) critical firing| CRITICAL | FIRING   |
| (5) de-escalation      | WARNING  | FIRING   |
| (4) (6) resolved       | INFO     | RESOLVED |

Emitted alerts use `metric="cpu_usage"` and are handed to `AlertRegistry`,
which dedupes, cooldowns, and fans them out over SSE (see Alert_Lifecycle.md).

## Rationale

Static thresholds are used here instead of the z-score baseline (CpuAnomalyAlert):
when the CPU saturates for long enough, the sliding-window baseline drifts up and
the anomaly detector stops firing on genuinely saturated machines. Absolute
boundaries cannot drift.
