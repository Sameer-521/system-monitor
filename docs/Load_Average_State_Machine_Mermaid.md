# Load Average State Machine

```mermaid
stateDiagram-v2
    [*] --> OK

    OK --> WARNING : 5m >= 1.5c, 14/18 ticks (3m)
    OK --> CRITICAL : 1m >= 3.0c, 9/12 ticks (2m)

    WARNING --> CRITICAL : 1m >= 3.0c, 9/12 ticks (2m)
    WARNING --> OK : 5m < 1.0c, 24/30 ticks (5m)
    WARNING --> WARNING : 5m >= 1.0c, recovery tick = false

    CRITICAL --> WARNING : 1m < 1.5c, 5/6 ticks (1m)
    CRITICAL --> CRITICAL : 1m >= 1.5c, recovery tick = false
```

- Window: rolling N-of-M tick classification, one tick per 10s (10 samples).
- Trigger windows: `warning_ticks` (maxlen 18), `critical_ticks` (maxlen 12).
- Recovery windows: `warning_recovery_ticks` (maxlen 30), `critical_recovery_ticks` (maxlen 6).
