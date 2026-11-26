# Interfaces (agreed Sobiya + Ritik). Owner changes it, tells the partner same day.

## Reading (what goes in SQLite payload and to ThingsBoard)
{"ts": <epoch ms, 13 digits>, "values": {ph, turbidity_ntu, tds_ppm, water_temp_c,
 flow_lpm, latitude, longitude, rssi_dbm, buffer_depth, seq}}
Batch = array of readings, oldest first.
- Model returns ts + values (ph, turbidity_ntu, tds_ppm, water_temp_c, flow_lpm, latitude,
  longitude) + top-level "severity" (0..1, NOT sent to cloud).
- Node adds rssi_dbm, buffer_depth, seq before insert().

## Model (src/models.py, Sobiya)
WaterModel(node_cfg, time_scale, start_hour)
.step(now_ms) -> reading dict       .post_event(event) -> bool       .severity

## Buffer (src/buffer.py, Ritik)
insert(reading), oldest_pending(n), mark_synced(ids), depth(), enforce_capacity()

## Link (src/mqtt_link.py, Ritik)
connect(), publish_batch(rows) -> True/False, block(), unblock()

## Node (src/node.py, Ritik)  -- used by main.py
Node(node_cfg, model, cfg, sample_interval_s)  .start()  .stop()  .link  .status() -> str

## Events: {"type": "rain_event", "node": "node-01", "peak_ntu": 600}
types: rain_event (peak_ntu, tau_min?), supply_interruption (duration_s),
network_outage (duration_s? auto-restores), network_restore. node may be "all".

## Log line
2026-11-19T10:02:14.120Z [node-01] [ONLINE ] message     (use src/logutil.log)
tags: ONLINE OFFLINE STATE REPLAY EVENT WARN ERROR EVICT AUTH

## Config: config/nodes.json  {"host","port","nodes":[{id,name,latitude,longitude,token,db_file}]}