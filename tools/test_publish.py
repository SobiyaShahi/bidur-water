import json, sys, time
import certifi
import paho.mqtt.client as mqtt

HOST = "mqtt.thingsboard.cloud"
PORT = 8883
TOKEN = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "test"

def reading(ts, ntu=4.0, ph=7.2, tds=180, flow=12.0):
    return {"ts": ts, "values": {"ph": ph, "turbidity_ntu": ntu, "tds_ppm": tds,
            "water_temp_c": 19.0, "flow_lpm": flow,
            "latitude": 27.9120, "longitude": 85.1480}}

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test-publish")
c.username_pw_set(TOKEN, "")
c.tls_set(ca_certs=certifi.where())
c.connect(HOST, PORT, 60)
c.loop_start()
time.sleep(1)

now = int(time.time() * 1000)          # 13 digits, milliseconds
T = "v1/devices/me/telemetry"

if mode == "test":                      # one live reading + old batch
    batch = [reading(now - 300000 + i * 10000, ntu=4 + i * 3) for i in range(30)]
    msgs = [reading(now)] + [batch]
elif mode == "wobble":                  # noise around 50 NTU
    msgs = [reading(now + i * 2000, ntu=[52, 48, 53, 47][i % 4]) for i in range(20)]
else:                                   # custom: mode = ntu,ph,tds,flow
    n, p, t, f = [float(x) for x in mode.split(",")]
    msgs = [reading(now, n, p, t, f)]

for m in msgs:
    info = c.publish(T, json.dumps(m), qos=1)
    info.wait_for_publish(timeout=30)
    print("published:", info.is_published())
    time.sleep(2 if mode == "wobble" else 0.2)
c.loop_stop()