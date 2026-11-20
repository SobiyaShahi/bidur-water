# Decisions

- Keep the initial tank model pure Python so simulation is deterministic and
  testable without a broker, database, or physical node.
- Represent flow in liters per second and simulation time in seconds; clamp
  tank level to zero and configured capacity after each step.
- Use JSON for scenarios and CSV for model output so the results are easy to
  inspect and plot.
- Keep credentials out of tracked configuration. Integration config refers to
  environment-variable names instead.
- Leave node, MQTT, buffering, SQL, and ThingsBoard integration behavior to the
  designated Ritik handoff rather than guessing hardware or deployment details.