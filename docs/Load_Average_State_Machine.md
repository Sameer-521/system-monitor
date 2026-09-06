# Load Average State Machine Specification

This document defines the state transition lifecycle, hysteresis rules, and tick counts for monitoring system load averages relative to host CPU capacity.

---

## State Transition Diagram

```
                                    (2) 1m > 3.0c, 12t/2m
      +---------------------------------------------------------------->-----------------+
      |                                                                                  v
+-----|--+----(1) 5m > 1.5c, 18t/3m----->+----------+----(3) 1m > 3.0c, 12t/2m----->+----------+
|   OK   |                               | WARNING  |                               | CRITICAL |
+--------+                               +----------+                               +----------+
      ^                                       |                                          |
      |                                       |                                          |
      +<--------(4) 5m < 1.0c, 30t/5m---------+
                                              +<----------(6) 1m < 1.5c, 6t/1m-----------+

(1) OK --> WARNING        5-min Load >  1.5 * Cores   18 ticks / 3m
(2) OK --> CRITICAL       1-min Load >  3.0 * Cores   12 ticks / 2m
(3) WARNING --> CRITICAL  1-min Load >  3.0 * Cores   12 ticks / 2m
(4) WARNING --> OK        5-min Load <  1.0 * Cores   30 ticks / 5m
(5) WARNING --> WARNING   5-min Load >= 1.0 * Cores   reset recovery ticks
(6) CRITICAL --> WARNING  1-min Load <  1.5 * Cores    6 ticks / 1m
(7) CRITICAL --> CRITICAL 1-min Load >= 1.5 * Cores   reset recovery ticks
```
