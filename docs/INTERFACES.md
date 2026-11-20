# Interfaces

## Scenario runner

`main.py` accepts a JSON scenario and writes CSV with the columns
`step,time_seconds,level_liters`. The model is deterministic and has no
hardware or network side effects.

## Node integration handoff

Ritik's `src/node.py` implementation should expose a node that can:

- read a node configuration and obtain secrets only from environment variables;
- produce timestamped numeric telemetry;
- send telemetry through the transport abstraction;
- tolerate transient transport failures without losing buffered samples.

`src/buffer.py` owns bounded buffering policy. `src/mqtt_link.py` owns MQTT
connection and publish behavior. Keep the simulation model independent of
these runtime integrations.

## ThingsBoard handoff

The example node configuration names environment variables, not credentials.
The expected telemetry key for the demo is `tank_level`; the integration
should agree with the ThingsBoard device profile before publishing.

## SQL handoff

The `sql/` directory is reserved for Ritik's schema and migration scripts.
Document timestamp units, device identity, and telemetry units alongside the
schema when it is added.