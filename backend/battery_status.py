import websocket
import json
import time

ROBOT_IP = "192.168.0.130"
WS_PORT = 5000

def receive(ws, timeout=10):
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except:
        return None

def listen_battery_info(ws, listen_duration=15):
    print("🔋 Listening for battery info...")
    start_time = time.time()
    while time.time() - start_time < listen_duration:
        res = receive(ws, timeout=2)
        if res:
            cmd = res.get("cmd")
            if cmd == "notify_battery_info":
                battery = res["data"].get("battery")
                status = res["data"].get("status")
                charging = "Yes" if status == 1 else "No"
                print(f"🔋 Battery: {battery}% | ⚡ Charging: {charging}")
                return
            else:
                print("📩 Received:", cmd)
        else:
            print("⌛ Waiting for battery info...")

    print("❌ Did not receive battery info in time.")

def main():
    try:
        ws = websocket.create_connection(f"ws://{ROBOT_IP}:{WS_PORT}")
        print("🔌 Connected to robot")
        listen_battery_info(ws)
        ws.close()
    except Exception as e:
        print("❌ Error:", e)

if __name__ == "__main__":
    main()