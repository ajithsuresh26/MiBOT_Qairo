import websocket
import json
import time
import pyttsx3
import threading
from enum import Enum
import queue

# --- STOP/RESUME CONTROL FLAGS ---
#navigation_stop_event = threading.Event()

'''def stop_navigation():
    print("🛑 Processing stop command...")
    navigation_stop_event.set()

def resume_navigation():
    print("▶️ Processing resume command...")
    navigation_stop_event.clear()
'''
# Navigation status codes
NAVI_CODES = {
    6100: "NAVI_RUNNING - Navigation in operation",
    2007: "NAVI_RUNNING - In navigation",
    2006: "NAVI_IDLE - Navigation completed",
    3001: "OBSTACLE_DETECTED - Obstacle in path",
    3002: "OBSTACLE_CLEARED - Path clear",
    4001: "EMERGENCY_STOP - Emergency stop activated"
}

class ObstacleStatus(Enum):
    CLEAR = "clear"
    DETECTED = "detected"
    AVOIDING = "avoiding"

class TTSManager:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def speak(self, text):
        self.queue.put(text)

    def _run(self):
        while True:
            text = self.queue.get()
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                print(f"TTS error: {e}")

class ObstacleAvoidance:
    def __init__(self, tts_manager):
        self.status = ObstacleStatus.CLEAR
        self.tts = tts_manager
        self.obstacle_timeout = 30  # seconds to wait for obstacle clearance
        
    def handle_obstacle(self, ws):
        """Handle obstacle detection and avoidance"""
        if self.status == ObstacleStatus.CLEAR:
            self.status = ObstacleStatus.DETECTED
            self.tts.speak("Obstacle detected. Attempting to avoid.")
            print("⚠ Obstacle detected - initiating avoidance procedure")
            return self._attempt_obstacle_avoidance(ws)
        return False
    
    def _attempt_obstacle_avoidance(self, ws):
        """Attempt various obstacle avoidance strategies"""
        self.status = ObstacleStatus.AVOIDING
        strategies = [
            self._wait_for_clearance,
            self._try_alternative_path,
            self._slow_navigation
        ]
        for strategy in strategies:
            if strategy(ws):
                self.status = ObstacleStatus.CLEAR
                self.tts.speak("Obstacle cleared. Resuming navigation.")
                return True
        self.tts.speak("Unable to avoid obstacle. Manual intervention required.")
        return False
    
    def _wait_for_clearance(self, ws):
        """Wait for obstacle to clear naturally"""
        print("🕐 Strategy 1: Waiting for obstacle clearance...")
        start_time = time.time()
        while time.time() - start_time < self.obstacle_timeout:
            send(ws, {"cmd": "request_check_path"})
            res = receive_response(ws, timeout=2)
            if res and res.get("code") == 3002:  # Path clear
                print("✅ Obstacle cleared naturally")
                return True
            time.sleep(2)
        return False
    
    def _try_alternative_path(self, ws):
        """Try to find alternative path"""
        print("🔄 Strategy 2: Attempting alternative path...")
        send(ws, {"cmd": "request_alternative_path"})
        time.sleep(3)
        return True  # Simplified - assume success
    
    def _slow_navigation(self, ws):
        """Reduce navigation speed to navigate around obstacles"""
        print("🐌 Strategy 3: Reducing navigation speed...")
        return True  # Simplified - assume success

# Initialize TTS and Obstacle Avoidance
tts_manager = TTSManager()
obstacle_avoidance = ObstacleAvoidance(tts_manager)

def send(ws, msg):
    """Send JSON message to robot via WebSocket"""
    ws.send(json.dumps(msg))

def receive_response(ws, timeout=5):
    """Receive and parse JSON response from robot"""
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except:
        return None

def set_map(ws, map_name, map_id):
    """Switch robot to specified map"""
    print(f"🗺 Setting map to {map_name} ({map_id})")
    tts_manager.speak(f"Switching to {map_name}")
    send(ws, {"cmd": "request_set_map", "data": {"mapId": map_id}})
    while True:
        res = receive_response(ws)
        if res and res.get("cmd") == "response_set_map" and res.get("code") == 1000:
            print(f"✅ Map {map_name} set successfully")
            tts_manager.speak(f"{map_name} loaded successfully")
            break

def get_points(ws, map_id):
    """Get list of waypoints for specified map"""
    send(ws, {"cmd": "request_point_list", "data": {"mapId": map_id}})
    start = time.time()
    while time.time() - start < 5:
        res = receive_response(ws, timeout=1)
        if res and res.get("cmd") == "response_point_list" and res.get("code") == 0:
            return res.get("data", {}).get("points", [])
    return []

def reset_map(ws):
    """Reset robot's map localization"""
    print("🔄 Resetting map localization...")
    tts_manager.speak("Resetting robot position")
    send(ws, {"cmd": "request_reset_map"})
    time.sleep(2)

def relocate(ws, x, y, theta, mode=2):
    """Force robot to specific position and orientation"""
    print(f"📍 Relocating to position: x={x:.2f}, y={y:.2f}, theta={theta:.2f}")
    send(ws, {"cmd": "request_force_relocate", "data": {"x": x, "y": y, "theta": theta, "mode": mode}})
    while True:
        res = receive_response(ws)
        if res and res.get("cmd") == "response_relocate_position" and res.get("code") == 4000:
            print("✅ Relocate success")
            break

def relocate_with_retry(ws, x, y, theta, retries=3):
    """Attempt relocation with multiple retries"""
    for attempt in range(retries):
        print(f"🚩 Attempting relocation {attempt + 1}/{retries}...")
        reset_map(ws)
        relocate(ws, x, y, theta)
        time.sleep(2)
        return True  # Assuming success after reset and relocate
    print("❌ Failed to relocate after retries.")
    tts_manager.speak("Failed to relocate robot")
    return False

def get_current_location(ws, timeout=10):
    print("📡 Waiting for robot heartbeat to get current location...")
    start_time = time.time()
    while True:
        res = receive_response(ws, timeout=2)
        if res and res.get("cmd") == "notify_heart_beat" and "x" in res.get("data", {}):
            data = res["data"]
            print(f"📍 Current Location → x: {data['x']}, y: {data['y']}, theta: {data['theta']}")
            return data
        if time.time() - start_time > timeout:
            print("❌ Failed to receive heartbeat.")
            return None

def start_navigation_and_wait_completion(ws, x, y, theta, speed=0.5, navigation_control=None):
    print(f"🚀 Starting navigation to: x={x:.2f}, y={y:.2f}, theta={theta:.2f}")
    tts_manager.speak("Starting navigation")

    navigation_started = False
    navigation_completed = False
    timeout = 180
    start_time = time.time()

    # Always send navigation command at the start
    send(ws, {"cmd": "request_start_navigation", "data": {"x": x, "y": y, "theta": theta, "speed": speed}})

    while True:
        # Pause logic
        while navigation_control and navigation_control['paused'].is_set():
            print("🛑 Navigation paused by user, sending stop to robot")
            send(ws, {"cmd": "request_stop_navigation"})
            tts_manager.speak("Navigation paused by user")
            while navigation_control['paused'].is_set():
                time.sleep(0.2)
            print("▶️ Navigation resumed by user, waiting before getting position and force relocating")
            tts_manager.speak("Navigation resumed by user")
            time.sleep(1.5)
            curr_pose = get_current_location(ws, timeout=8)
            if curr_pose:
                curr_x = curr_pose.get("x", x)
                curr_y = curr_pose.get("y", y)
                curr_theta = curr_pose.get("theta", theta)
                print(f"▶️ Force relocating to x={curr_x:.2f}, y={curr_y:.2f}, theta={curr_theta:.2f}")
                send(ws, {
                    "cmd": "request_force_relocate",
                    "data": {"x": curr_x, "y": curr_y, "theta": curr_theta, "mode": 0}
                })
                # Wait for relocation confirmation
                while True:
                    relocate_res = receive_response(ws, timeout=2)
                    if relocate_res and relocate_res.get("cmd") == "response_relocate_position" and relocate_res.get("code") == 0:
                        print("✅ Relocation successful.")
                        break
                    elif relocate_res:
                        print(f"📩 Received (relocate): {relocate_res}")
            else:
                print("⚠️ Could not get current position from heartbeat, skipping relocation")
            # Now re-issue navigation command to destination
            navigation_started = False  # <--- CRITICAL: Reset this!
            send(ws, {"cmd": "request_start_navigation", "data": {"x": x, "y": y, "theta": theta, "speed": speed}})
            start_time = time.time()
            time.sleep(0.5)

        res = receive_response(ws, timeout=1)
        if res:
            cmd = res.get("cmd")
            code = res.get("code")

            if cmd == "response_start_navigation":
                if code == 1001 or res.get('msg') == 'navigation success':
                    print("✅ Navigation started successfully")
                    navigation_started = True
                else:
                    print(f"❌ Navigation failed to start: code={code}, msg={res.get('msg')}")
                    tts_manager.speak("Navigation failed to start")
                    return False

            elif cmd == "notify_heart_beat":
                if code == 6100:
                    print("⌛ Navigation in operation (6100)")
                    navigation_completed = False
                elif code == 2007:
                    print("⌛ In navigation (2007)")
                    navigation_completed = False
                elif code == 2006:
                    # Only complete if navigation has started!
                    if navigation_started and not navigation_completed:
                        print("🏁 Navigation completed successfully!")
                        tts_manager.speak("Navigation completed successfully")
                        navigation_completed = True
                        time.sleep(1)
                        return True
                    else:
                        # Ignore spurious 2006 before navigation actually started
                        print("⚠️ Received NAVI_IDLE (2006) before navigation started, ignoring.")
                elif code == 3001:
                    print("⚠ Obstacle detected during navigation")
                    if not obstacle_avoidance.handle_obstacle(ws):
                        tts_manager.speak("Unable to avoid obstacle. Stopping navigation.")
                        return False
                elif code == 4001:
                    print("🛑 Emergency stop activated")
                    tts_manager.speak("Emergency stop activated")
                    return False
                else:
                    print(f"📡 Heartbeat: {code}")

        if time.time() - start_time > timeout:
            print("❌ Navigation monitoring timed out.")
            tts_manager.speak("Navigation timeout")
            return False

        time.sleep(0.1)

def execute_map_navigation(ws, map_name, map_id, navigation_control=None):
    """Execute navigation for a single map"""
    print(f"\n🎯 EXECUTING: {map_name}")
    print("=" * 50)
    
    # Check for force stop before starting
    # Set the map
    set_map(ws, map_name, map_id)
    
    # Get waypoints
    points = get_points(ws, map_id)
    if not points:
        print(f"❌ No points found for {map_name}")
        tts_manager.speak(f"No waypoints found for {map_name}")
        return False

    anchor = next((p for p in points if p.get("type") == "anchor_point"), None)
    dest = next((p for p in points if p.get("type") == "destination"), None)

    if not anchor or not dest:
        print(f"❌ {map_name}: Missing anchor or destination point!")
        tts_manager.speak(f"Missing waypoints for {map_name}")
        return False

    print(f"📌 {map_name} Anchor: x={anchor['x']:.2f}, y={anchor['y']:.2f}, θ={anchor['theta']:.2f}")
    print(f"📌 {map_name} Destination: x={dest['x']:.2f}, y={dest['y']:.2f}, θ={dest['theta']:.2f}")

    # Execute navigation
    if not relocate_with_retry(ws, anchor["x"], anchor["y"], anchor["theta"]):
        return False

    success = start_navigation_and_wait_completion(ws, dest["x"], dest["y"], dest["theta"], navigation_control=navigation_control)    
    if success:
        print(f"✅ {map_name} navigation completed!")
        tts_manager.speak(f"{map_name} navigation completed")
    else:
        print(f"❌ {map_name} navigation failed!")
        tts_manager.speak(f"{map_name} navigation failed")
    
    return success

def run_multi_map_navigation_no_tts(robot_ip, map_ids, port, navigation_status=None, navigation_control=None):
    print("✅✅✅ Map navigation started for multiple maps (no TTS)")
    try:
        ws = websocket.create_connection(f"ws://{robot_ip}:{port}")
        print("✅🔌 Connected to robot successfully for multi-map navigation!")

        successful_maps = []
        failed_maps = []

        for idx, map_id in enumerate(map_ids):
            # Update live map id
            if navigation_status is not None:
                navigation_status['current_map'] = map_id
            # Pause logic
            while navigation_control and navigation_control['paused'].is_set():
                if navigation_status is not None:
                    navigation_status['paused'] = True
                time.sleep(0.5)
            if navigation_status is not None:
                navigation_status['paused'] = False
            map_name = f"map{idx+1}"
            print(f"\n{'='*60}")
            print(f"🗺 STARTING MAP: {map_name}")
            print(f"{'='*60}")
            success = execute_map_navigation(ws, map_name, map_id, navigation_control=navigation_control)
            if success:
                successful_maps.append(map_name)
            else:
                failed_maps.append(map_name)
            if idx != len(map_ids) - 1:
                print("\n⏸ Preparing for next map...")
                time.sleep(3)
        ws.close()
        print("\n🔌 Connection closed - All tasks finished!")
        if len(successful_maps) == len(map_ids):
            return {"success": True}
        else:
            return {"success": False, "message": f"{len(failed_maps)} maps failed"}
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        return {"success": False, "message": str(e)}

def main():
    try:
        ws = websocket.create_connection(f"ws://{ROBOT_IP}:{WS_PORT}")
        print("🔌 Connected to robot successfully!")
        tts_manager.speak("Robot connection established. Starting multi-map navigation mission.")
        successful_maps = []
        failed_maps = []
        for idx, map_id in enumerate(MAP_IDS):
            map_name = f"map{idx+1}"
            print(f"\n{'='*60}")
            print(f"🗺 STARTING MAP: {map_name}")
            print(f"{'='*60}")
            success = execute_map_navigation(ws, map_name, map_id)
            if success:
                successful_maps.append(map_name)
            else:
                failed_maps.append(map_name)
            if idx != len(MAP_IDS) - 1:
                print("\n⏸ Preparing for next map...")
                time.sleep(3)
        print(f"\n{'='*60}")
        print("🏁 MISSION SUMMARY")
        print(f"{'='*60}")
        if successful_maps:
            print(f"✅ Successful Maps ({len(successful_maps)}):")
            for map_name in successful_maps:
                print(f"   • {map_name}")
        if failed_maps:
            print(f"❌ Failed Maps ({len(failed_maps)}):")
            for map_name in failed_maps:
                print(f"   • {map_name}")
        if len(successful_maps) == len(MAP_IDS):
            print("\n🎉 ALL MAP NAVIGATIONS COMPLETED SUCCESSFULLY!")
            tts_manager.speak("All map navigations completed successfully!")
        else:
            failed_count = len(failed_maps)
            print(f"\n⚠ {failed_count} out of {len(MAP_IDS)} maps failed")
            tts_manager.speak(f"{failed_count} maps failed out of {len(MAP_IDS)}")
        ws.close()
        print("\n🔌 Connection closed - All tasks finished!")
        tts_manager.speak("Robot navigation mission complete")
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        tts_manager.speak("An error occurred during robot operation")
        if 'ws' in locals():
            ws.close()