import websocket
import json
import time

ROBOT_IP = "192.168.0.130"
WS_PORT = 5000

def send(ws, msg):
    ws.send(json.dumps(msg))

def receive_possible_maps():
    try:
        ws = websocket.create_connection(f"ws://{ROBOT_IP}:{WS_PORT}")
        print("🔌 Connected to robot")

        # Try one of these map list command variants:
        test_commands = [
            {"cmd": "request_list_maps"},
            {"cmd": "request_map_list"},
            {"cmd": "get_map_list"},
            {"cmd": "request_get_map_list"},
        ]

        for cmd in test_commands:
            print(f"📤 Sending command: {cmd['cmd']}")
            send(ws, cmd)
            time.sleep(1)

        print("⏳ Listening for map data...")

        start_time = time.time()
        timeout = 10
        found = False

        while time.time() - start_time < timeout:
            try:
                response = ws.recv()
                data = json.loads(response)
                print("📩 Received:")

                # Look for a map list inside the message
                if "maps" in data.get("data", {}):
                    maps = data["data"]["maps"]
                    if maps:
                        print("\n🗺 Maps Found:")
                        for m in maps:
                            print(f" - {m.get('name')} : {m.get('id')}")
                        found = True
                        break

                elif "mapList" in data.get("data", {}):
                    maps = data["data"]["mapList"]
                    if maps:
                        print("\n🗺 Maps Found:")
                        for m in maps:
                            print(f" - {m.get('name')} : {m.get('mapId')}")
                        found = True
                        break

            except Exception as e:
                print("⚠ Error or timeout:", e)
                break

        if not found:
            print("❌ No map data received. Try checking robot state or credentials.")

        ws.close()

    except Exception as e:
        print("❌ Connection error:", e)

if __name__ == "__main__":
    receive_possible_maps()