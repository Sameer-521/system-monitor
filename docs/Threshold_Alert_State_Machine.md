# Threshold State Machine Specification — `ThresholdAlert`

This document defines the generic ok/warning/critical state machine in
`app/alerts/threshold.py`: static thresholds, hysteresis rules, and N-of-M sliding
windows over bucketed metric values. `HighCpuUsage` (app/alerts/high_cpu_usage.py) and
`HighIowait` (app/alerts/high_iowait.py) are thin configured subclasses; the machine
itself is metric-agnostic. `CpuUsageState` and `IowaitState` are aliases of the shared
`ThresholdState` enum.

---

## Configurations

| config               | HighCpuUsage            | HighIowait              |
| -------------------- | ----------------------- | ----------------------- |
| emitted `metric`     | `cpu_usage`             | `iowait`                |
| snapshot key         | `cpu.usage_percentage`  | `cpu.iowait`            |
| bucket reducer       | mean of samples         | max across cores        |
| warning / critical   | 70 / 90                 | 30 / 50                 |
| bucket               | 10 samples = 10 seconds | 10 samples = 10 seconds |

Both instances share the same N/M windows (see below). The windows are time-based, not
metric-based: at a 1s poll interval, "5 of 6 buckets" means "50s of breach within a 60s
window" regardless of which metric is being measured.

## State Transition Diagram

```
                                  (2) value >= crit, 3/4b (bypasses WARNING)
       +--------------------------------------------->----------------------------------------------+
       |                                                                                            v
  +----|-----+------(1) value >= warn, 5/6b---->+----------+------(3) value >= crit, 3/4b---->+----------+
  |    OK    |                                  | WARNING  |                                  | CRITICAL |
  +----------+                                  +----------+                                  +----------+
   ^ ^                                            |    ^                                        |     |
   | |                                            |    |                                        |     |
   | +<-------(4) value < warn, 6/8b--------------+    +<--------(5) value < crit, 5/6b---------+     |
   |                                                                                                  |
   +<----------(6) value < warn, crit 5/6b AND warn 6/8b in same pass---------------------------------+

(1) OK --> WARNING        value >= warn   5 of 6 buckets
(2) OK --> CRITICAL       value >= crit   3 of 4 buckets (bypasses WARNING entirely)
(3) WARNING --> CRITICAL  value >= crit   3 of 4 buckets
(4) WARNING --> OK        value < warn    6 of 8 buckets
(5) CRITICAL --> WARNING  value < crit    5 of 6 buckets (warn recovery not met yet)
(6) CRITICAL --> OK       value < warn    crit recovery 5/6 AND warn recovery 6/8 in the same pass
(7) WARNING --> WARNING   value >= warn   recovery tick = false
(8) CRITICAL --> CRITICAL value >= crit   recovery tick = false
```

- `value` = reduced bucket value (mean or max per the configuration above).
- `N/Mb` = N breach buckets within a sliding window of M buckets.

## Sliding Windows

| window                     | N of M | condition                        |
| -------------------------- | ------ | -------------------------------- |
| `critical_ticks`           | 3 / 4  | bucket value >= crit             |
| `warning_ticks`            | 5 / 6  | bucket value >= warn             |
| `critical_recovery_ticks`  | 5 / 6  | state = CRITICAL, value < crit   |
| `warning_recovery_ticks`   | 6 / 8  | state != OK, value < warn        |

- Window appends are gated by the **current** state, not the checked transition:
  `warning_recovery` keeps accumulating while CRITICAL (state != OK), which is
  what allows (6) — both recovery windows fill in parallel below the warning threshold.
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

Emitted alerts use the configured `metric` and `extra` key and are handed to
`AlertRegistry`, which dedupes, cooldowns, and fans them out over SSE (see
Alert_Lifecycle.md).

## Rationale

For HighCpuUsage, static thresholds are used instead of the z-score baseline
(CpuAnomalyAlert): when the CPU saturates for long enough, the sliding-window baseline
drifts up and the anomaly detector stops firing on genuinely saturated machines.
Absolute boundaries cannot drift.

For the shared N/M defaults, the justification is empirical: the N-of-M windows are
what absorb bucket noise — burst immunity (isolated spikes never accumulate enough
breach buckets), tolerance to mid-stall dips (a strict M-of-M rule would miss a stall
with a single quiet bucket), and ~30s detection latency for sustained stalls. The max
reducer in HighIowait makes every bucket the worst core's value, which makes this noise
rejection more important, not less.

Known caveat: with the max reducer, a single core that blips iowait every bucket keeps
the signal permanently breached and the alert never resolves. No window choice fixes
that — it is a reducer/threshold question. Per-host tuning of thresholds and windows is
deferred to the settings layer.
