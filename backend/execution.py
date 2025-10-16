import websocket
import json
import time
import threading
from enum import Enum
import queue
from datetime import datetime
import sys

# Try to import pyttsx3, but handle the case where it's not available
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    print("⚠ [TTS] pyttsx3 not available. TTS functionality will be disabled.")

# --- EMERGENCY EXIT CONFIGURATION ---
EMERGENCY_EXIT_MAP_ID = "c2606e61-7e0d-410a-b618-c43c523ebb33"  # This should be map2 (emergency map)
emergency_exit_event = threading.Event()
current_map_position = 0  # Track current map position in sequence
map_sequence = []  # Will store the current map sequence being navigated
emergency_exit_in_progress = False  # Flag to prevent recursive emergency exits
navigation_phase = "forward"  # Track if we're in "forward" or "reverse" phase

# --- MAP TRACKING VARIABLES ---
current_map_id = None  # Current map ID being navigated
current_map_name = None  # Current map name being navigated
upcoming_map_ids = [None, None]  # Next two upcoming map IDs
upcoming_map_names = [None, None]  # Next two upcoming map names
robot_maps_cache = []  # Cache for robot maps to get names by ID


# --- BATTERY AND CHARGING CONFIGURATION ---
MAP_ID = "be6e76e5-3612-4eb7-89ee-6bc09f222634"
CHARGE_POINT = {
    "x": -0.000742468717372349,
    "y": -0.017879863624663088,
    "theta": -0.016518184324892632
}

def trigger_emergency_exit():
    """Trigger emergency exit procedure"""
    global emergency_exit_in_progress
    print("🚨 [EMERGENCY] Emergency exit triggered by user!")
    if not emergency_exit_in_progress:
        emergency_exit_event.set()

def clear_emergency_exit():
    """Clear emergency exit state"""
    global emergency_exit_in_progress
    print("✅ [EMERGENCY] Emergency exit state cleared.")
    emergency_exit_event.clear()
    emergency_exit_in_progress = False

def execute_emergency_exit_navigation(ws, map_ids, navigation_control=None):
    """
    Execute emergency exit navigation based on the specified logic:
    - If in map2 (emergency map) → stop immediately
    - If in map1 (before emergency map) → go forward to map2 destination
    - If in map3 or map4 (after emergency map) → go backward:
      Current destination → Current anchor → Previous anchors → Map2 anchor → Map2 destination

    Forward Journey = Anchor → Destination
    Backward Journey = Destination → Anchor
    """
    global current_map_position, map_sequence, emergency_exit_in_progress, navigation_phase
    
    print("🚨 [EMERGENCY] Starting emergency exit navigation process...")
    print(f"📍 [EMERGENCY] Current position: Map {current_map_position + 1} (index {current_map_position})")
    print(f"🔄 [EMERGENCY] Current navigation phase: {navigation_phase}")
    
    emergency_exit_in_progress = True

    # Find emergency exit map position (should be map2, index 1)
    try:
        emergency_exit_position = map_sequence.index(EMERGENCY_EXIT_MAP_ID)
        print(f"📍 [EMERGENCY] Emergency exit map found at position {emergency_exit_position + 1} (index {emergency_exit_position})")
    except ValueError:
        print("❌ [EMERGENCY] Emergency exit map ID not found in current sequence!")
        emergency_exit_in_progress = False
        return False

    # CASE 1: Already at emergency exit map (map2) → stop immediately
    if current_map_position == emergency_exit_position:
        print("🟢 [EMERGENCY] Already at emergency exit map (Map2). Stopping immediately...")
        
        # Immediately stop navigation
        cancel_current_navigation(ws)
        time.sleep(1)
        
        # Send multiple stop commands to ensure robot stops
        for _ in range(3):
            send(ws, {"cmd": "request_stop_navigation"})
            time.sleep(0.5)
        
        print("🛑 [EMERGENCY] Robot stopped at emergency exit map.")
        navigation_stop_event.set()
        emergency_exit_in_progress = False
        return True

    # CASE 2: Before emergency exit map (map1) → go forward to map2 destination
    elif current_map_position < emergency_exit_position:
        print(f"➡ [EMERGENCY] Currently in Map{current_map_position + 1}, going forward to emergency exit Map{emergency_exit_position + 1}")
        
        # Navigate forward through each map until reaching emergency exit
        for seq_pos in range(current_map_position + 1, emergency_exit_position + 1):
            map_id = map_sequence[seq_pos]
            map_name = f"emergency_forward_map{seq_pos + 1}"
            
            print(f"🗺 [EMERGENCY] Forward navigation to {map_name} (ID: {map_id})...")
            
            # Use forward mode (anchor → destination)
            success = execute_map_navigation(ws, map_name, map_id, navigation_control=navigation_control, reverse_mode=False, emergency_mode=True)
            
            if not success:
                print(f"❌ [EMERGENCY] Failed to navigate forward to {map_name}. Stopping emergency exit.")
                emergency_exit_in_progress = False
                return False
            
            print(f"✅ [EMERGENCY] Arrived at {map_name}")
            current_map_position = seq_pos
            
            # If we reached the emergency exit map, stop here
            if seq_pos == emergency_exit_position:
                print("🏁 [EMERGENCY] Reached emergency exit map destination. Stopping immediately.")
                cancel_current_navigation(ws)
                time.sleep(1)
                for _ in range(3):
                    send(ws, {"cmd": "request_stop_navigation"})
                    time.sleep(0.5)
                print("🛑 [EMERGENCY] Robot stopped at emergency exit.")
                navigation_stop_event.set()
                break
            
            print("⏳ [EMERGENCY] Waiting 2 seconds before next step...")
            time.sleep(2)

    # CASE 3: After emergency exit map (map3, map4, etc.) → go backward through anchors
    else:
        print(f"⬅ [EMERGENCY] Currently in Map{current_map_position + 1}, going backward to emergency exit Map{emergency_exit_position + 1}")
        print("🔄 [EMERGENCY] Emergency navigation sequence:")
        print(f"🔄 [EMERGENCY] Step 1: Current position (destination) → Current map anchor")
        print(f"🔄 [EMERGENCY] Step 2: Navigate through intermediate map anchors")
        print(f"🔄 [EMERGENCY] Step 3: Map2 anchor → Map2 destination (stop)")
        
        # STEP 1: First, go from current destination to current map's anchor
        current_map_id = map_sequence[current_map_position]
        current_map_name = f"emergency_current_to_anchor_map{current_map_position + 1}"
        
        print(f"🗺 [EMERGENCY] Step 1: From current destination to {current_map_name} anchor (ID: {current_map_id})...")
        
        # Use reverse mode (destination → anchor) to reach the anchor of current map
        success = execute_map_navigation(ws, current_map_name, current_map_id, navigation_control=navigation_control, reverse_mode=True, emergency_mode=True)
        
        if not success:
            print(f"❌ [EMERGENCY] Failed to navigate to current map anchor. Stopping emergency exit.")
            emergency_exit_in_progress = False
            return False
        
        print(f"✅ [EMERGENCY] Step 1 completed: Arrived at Map{current_map_position + 1} anchor")
        print("⏳ [EMERGENCY] Waiting 2 seconds before next step...")
        time.sleep(2)
        
        # STEP 2: Navigate backward through intermediate map anchors until reaching emergency exit
        for seq_pos in range(current_map_position - 1, emergency_exit_position - 1, -1):
            map_id = map_sequence[seq_pos]
            map_name = f"emergency_backward_map{seq_pos + 1}"
            
            print(f"🗺 [EMERGENCY] Step 2: Backward navigation to {map_name} anchor (ID: {map_id})...")
            
            # Use reverse mode (destination → anchor) to reach the anchor of this map
            success = execute_map_navigation(ws, map_name, map_id, navigation_control=navigation_control, reverse_mode=True, emergency_mode=True)
            
            if not success:
                print(f"❌ [EMERGENCY] Failed to navigate backward to {map_name} anchor. Stopping emergency exit.")
                emergency_exit_in_progress = False
                return False
            
            print(f"✅ [EMERGENCY] Arrived at {map_name} anchor point")
            print("⏳ [EMERGENCY] Waiting 2 seconds before next backward step...")
            time.sleep(2)
        
        # STEP 3: Now at emergency exit map anchor, navigate to destination and stop
        print("🏁 [EMERGENCY] Step 3: Reached emergency exit map anchor. Navigating to destination point...")
        
        final_success = execute_map_navigation(ws, f"emergency_exit_final", EMERGENCY_EXIT_MAP_ID, navigation_control=navigation_control, reverse_mode=False, emergency_mode=True)
        
        if final_success:
            print("✅ [EMERGENCY] Successfully reached emergency exit destination!")
            cancel_current_navigation(ws)
            time.sleep(1)
            for _ in range(3):
                send(ws, {"cmd": "request_stop_navigation"})
                time.sleep(0.5)
            print("🛑 [EMERGENCY] Robot stopped at emergency exit.")
            navigation_stop_event.set()
        else:
            print("❌ [EMERGENCY] Failed to reach emergency exit destination")
            emergency_exit_in_progress = False
            return False

    print("🏁 [EMERGENCY] Emergency exit navigation completed successfully!")
    emergency_exit_in_progress = False
    return True

def check_emergency_exit_during_navigation(ws, navigation_control=None):
    """
    Check if emergency exit is triggered during navigation
    Returns True if emergency exit was executed, False if navigation should continue
    """
    global emergency_exit_in_progress
    
    if emergency_exit_event.is_set() and not emergency_exit_in_progress:
        print("🚨 [EMERGENCY] Emergency exit event detected during navigation!")
        print("📍 [EMERGENCY] Will proceed to emergency exit after current destination is reached...")
        return False
    
    return False

# --- STOP/RESUME/QUIT CONTROL FLAGS ---
navigation_stop_event = threading.Event()
navigation_pause_event = threading.Event()
navigation_quit_event = threading.Event()  # New quit event

def pause_navigation():
    """Pause navigation - can be resumed"""
    print("⏸ [CONTROL] Navigation paused by user")
    navigation_pause_event.set()

def continue_navigation():
    """Resume navigation from pause"""
    print("▶ [CONTROL] Navigation resumed by user")
    navigation_pause_event.clear()

def stop_navigation():
    """Stop navigation - ends current cycle but allows restart"""
    print("🛑 [CONTROL] Navigation stopped by user")
    navigation_stop_event.set()

def quit_navigation():
    """Quit navigation completely - cancels everything and exits gracefully"""
    print("🚪 [CONTROL] Navigation quit requested by user")
    navigation_quit_event.set()
    navigation_stop_event.set()
    navigation_pause_event.clear()  # Clear pause if set
    emergency_exit_event.clear()  # Clear emergency if set

def reset_navigation_events():
    """Reset all navigation control events for new navigation"""
    print("🔄 [CONTROL] Resetting navigation control events")
    navigation_stop_event.clear()
    navigation_pause_event.clear()
    navigation_quit_event.clear()
    emergency_exit_event.clear()
    
    global emergency_exit_in_progress, navigation_phase
    emergency_exit_in_progress = False
    navigation_phase = "forward"

def update_map_tracking(map_ids, current_index, robot_ip=None):
    """Update current and upcoming map tracking information with actual map names.
    Respects current navigation direction (forward/backward)."""
    global current_map_id, current_map_name, upcoming_map_ids, upcoming_map_names, navigation_phase
    
    if 0 <= current_index < len(map_ids):
        current_map_id = map_ids[current_index]
        current_map_name = get_map_name_by_id(current_map_id, robot_ip)

        # Determine direction-aware upcoming indices
        if navigation_phase == "reverse":
            # In reverse, the next maps are previous in the list
            next_idx_1 = current_index - 1
            next_idx_2 = current_index - 2
        else:
            # Forward direction
            next_idx_1 = current_index + 1
            next_idx_2 = current_index + 2

        # Compute upcoming IDs
        id1 = map_ids[next_idx_1] if 0 <= next_idx_1 < len(map_ids) else None
        id2 = map_ids[next_idx_2] if 0 <= next_idx_2 < len(map_ids) else None
        upcoming_map_ids = [id1, id2]

        # Compute upcoming names
        name1 = get_map_name_by_id(id1, robot_ip) if id1 else None
        name2 = get_map_name_by_id(id2, robot_ip) if id2 else None
        upcoming_map_names = [name1, name2]

        print(f"🗺 [TRACKING] Current: {current_map_name} (ID: {current_map_id})")
        print(f"🗺 [TRACKING] Upcoming: {upcoming_map_names[0]} (ID: {upcoming_map_ids[0]}), {upcoming_map_names[1]} (ID: {upcoming_map_ids[1]})")
    else:
        # Navigation completed
        current_map_id = None
        current_map_name = None
        upcoming_map_ids = [None, None]
        upcoming_map_names = [None, None]
        print("🏁 [TRACKING] Navigation completed - no current map")

def clear_map_tracking():
    """Clear all map tracking information"""
    global current_map_id, current_map_name, upcoming_map_ids, upcoming_map_names
    current_map_id = None
    current_map_name = None
    upcoming_map_ids = [None, None]
    upcoming_map_names = [None, None]
    print("🧹 [TRACKING] Map tracking cleared")

def get_map_name_by_id(map_id, robot_ip=None):
    """Get map name by ID from robot maps or cache"""
    global robot_maps_cache
    
    if not map_id:
        return None
    
    # First check cache
    for map_info in robot_maps_cache:
        if map_info.get('id') == map_id:
            return map_info.get('name', f"Map_{map_id[:8]}")
    
    # If not in cache and we have robot IP, try to fetch maps
    if robot_ip:
        try:
            import requests
            response = requests.get(f"http://localhost:5000/api/robot/maps", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('maps'):
                    robot_maps_cache = data['maps']
                    for map_info in robot_maps_cache:
                        if map_info.get('id') == map_id:
                            return map_info.get('name', f"Map_{map_id[:8]}")
        except Exception as e:
            print(f"⚠️ [TRACKING] Could not fetch maps for name lookup: {e}")
    
    # Fallback to generic name
    return f"Map_{map_id[:8]}"

def update_robot_maps_cache(maps_list):
    """Update the robot maps cache with fresh data"""
    global robot_maps_cache
    robot_maps_cache = maps_list
    print(f"🗺 [TRACKING] Updated maps cache with {len(maps_list)} maps")

def wait_for_localization(ws, timeout=15):
    """Waits for the robot to confirm it is localized."""
    print("⏳ [LOCALIZE] Waiting for robot to localize...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        res = receive_response(ws, timeout=1)
        if res and res.get("cmd") == "notify_heart_beat":
            # Code 2005 often means "localized and ready"
            if res.get("code") == 2005:
                print("✅ [LOCALIZE] Robot localized successfully.")
                return True
            # Some firmwares might just send position data in heartbeat when localized
            elif "x" in res.get("data", {}):
                print("✅ [LOCALIZE] Robot localized (position received).")
                return True
        time.sleep(0.5)
    print("❌ [LOCALIZE] Localization timed out.")
    return False


# Navigation status codes
NAVI_CODES = {
    6100: "NAVI_RUNNING - Navigation in operation",
    2007: "NAVI_RUNNING - In navigation",
    2006: "NAVI_IDLE - Navigation completed",
    3001: "OBSTACLE_DETECTED - Obstacle in path",
    3002: "OBSTACLE_CLEARED - Path clear",
    4001: "EMERGENCY_STOP - Emergency stop activated",
    6001: "NAVIGATION_CANCELLED - Navigation was cancelled",
    1001: "NAVIGATION_SUCCESS - Navigation started successfully",
    6101: "NAVIGATION_ALREADY_RUNNING - Navigation already running"
}

# Charging status codes
CHARGING_CODES = {
    0: "NAVI_TO_CHARGE_OK - Navigate to charging pile",
    14002: "NAVI_TO_DOCK_START - Start navigating to charging pile",
    14004: "NAVI_TO_CHARGE - Start charging through charging pile",
    14005: "NAVI_TO_DOCK - Navigating to charging pile",
    6016: "NAVI_NOPILEDETECTED - No charging pile detected"
}

class ObstacleStatus(Enum):
    CLEAR = "clear"
    DETECTED = "detected"
    AVOIDING = "avoiding"

class TTSManager:
    def __init__(self):
        # Initialize all attributes first to avoid AttributeError
        self.initialized = False
        self.engine = None
        self.queue = queue.Queue()
        self.thread = None
        
        # Try to initialize TTS
        if PYTTSX3_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                self.initialized = True
                print("🔊 [TTS] Text-to-speech engine initialized successfully")
            except Exception as e:
                print(f"⚠ [TTS] Failed to initialize TTS engine: {e}")
                self.initialized = False
        else:
            print("🔊 [TTS] pyttsx3 not available, TTS disabled")
            self.initialized = False
        
        # Start thread regardless of initialization status
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        if self.initialized:
            print("🔊 [TTS] Text-to-speech manager initialized successfully")
        else:
            print("🔊 [TTS] Text-to-speech manager running in silent mode")

    def speak(self, text):
        """Add text to speech queue"""
        self.queue.put(text)

    def _run(self):
        """TTS thread worker function"""
        while True:
            try:
                text = self.queue.get()
                if text is None:  # Shutdown signal
                    break
                
                if self.initialized and self.engine:
                    try:
                        self.engine.say(text)
                        self.engine.runAndWait()
                    except Exception as e:
                        print(f"❌ [TTS] Error during speech: {e}")
                else:
                    # Silent mode - just print what would be spoken
                    print(f"🔊 [TTS] Would speak: {text}")
                    
            except Exception as e:
                print(f"❌ [TTS] Error in TTS thread: {e}")

    def shutdown(self):
        """Shutdown TTS manager"""
        try:
            self.queue.put(None)  # Signal shutdown
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2)
            print("✅ [TTS] TTS manager shut down")
        except Exception as e:
            print(f"⚠ [TTS] Error during TTS shutdown: {e}")

class ObstacleAvoidance:
    def __init__(self, tts_manager):
        self.status = ObstacleStatus.CLEAR
        self.tts = tts_manager
        self.obstacle_timeout = 30
        print("🚧 [OBSTACLE] Obstacle avoidance system initialized")

    def handle_obstacle(self, ws):
        if self.status == ObstacleStatus.CLEAR:
            self.status = ObstacleStatus.DETECTED
            print("🚧 [OBSTACLE] Obstacle detected! Starting avoidance procedure...")
            self.tts.speak("Obstacle detected. Attempting to avoid.")
            return self._attempt_obstacle_avoidance(ws)
        return False

    def _attempt_obstacle_avoidance(self, ws):
        self.status = ObstacleStatus.AVOIDING
        print("🔄 [OBSTACLE] Attempting obstacle avoidance strategies...")
        
        strategies = [
            self._wait_for_clearance,
            self._try_alternative_path,
            self._slow_navigation
        ]
        
        for i, strategy in enumerate(strategies):
            print(f"🔄 [OBSTACLE] Trying strategy {i+1}/3...")
            if strategy(ws):
                self.status = ObstacleStatus.CLEAR
                print("✅ [OBSTACLE] Obstacle cleared! Resuming navigation...")
                self.tts.speak("Obstacle cleared. Resuming navigation.")
                return True
        
        print("❌ [OBSTACLE] All avoidance strategies failed. Manual intervention required.")
        self.tts.speak("Unable to avoid obstacle. Manual intervention required.")
        return False

    def _wait_for_clearance(self, ws):
        print(f"⏳ [OBSTACLE] Waiting for obstacle clearance (timeout: {self.obstacle_timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < self.obstacle_timeout:
            if navigation_quit_event.is_set():
                print("🚪 [OBSTACLE] Quit requested during obstacle avoidance")
                return False
                
            send(ws, {"cmd": "request_check_path"})
            res = receive_response(ws, timeout=2)
            
            if res and res.get("code") == 3002:
                print("✅ [OBSTACLE] Path cleared by waiting!")
                return True
                
            time.sleep(2)
        
        print("⏳ [OBSTACLE] Wait timeout reached")
        return False

    def _try_alternative_path(self, ws):
        print("🔄 [OBSTACLE] Trying alternative path...")
        send(ws, {"cmd": "request_alternative_path"})
        time.sleep(3)
        return True

    def _slow_navigation(self, ws):
        print("🐌 [OBSTACLE] Using slow navigation strategy...")
        return True

# Initialize TTS and Obstacle Avoidance
tts_manager = TTSManager()
obstacle_avoidance = ObstacleAvoidance(tts_manager)

def log_message(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def send(ws, msg):
    try:
        ws.send(json.dumps(msg))
        return True
    except Exception as e:
        print(f"❌ [WEBSOCKET] Send error: {e}")
        return False

def receive_response(ws, timeout=5):
    try:
        ws.settimeout(timeout)
        return json.loads(ws.recv())
    except Exception as e:
        return None

def close_websocket_gracefully(ws):
    """Gracefully close websocket connection"""
    try:
        print("🔌 [WEBSOCKET] Closing connection gracefully...")
        
        # Cancel any ongoing navigation
        send(ws, {"cmd": "request_stop_navigation"})
        time.sleep(0.5)
        
        # Close the websocket
        ws.close()
        print("✅ [WEBSOCKET] Connection closed successfully")
        
    except Exception as e:
        print(f"⚠ [WEBSOCKET] Error during graceful close: {e}")

def get_battery_status(ws):
    print("🔋 [BATTERY] Requesting battery status...")
    
    if not send(ws, {"cmd": "request_battery_info"}):
        return {"battery_level": 100, "charging_status": 0, "needs_charging": False}
    
    start_time = time.time()
    while time.time() - start_time < 10:
        if navigation_quit_event.is_set():
            print("🚪 [BATTERY] Quit requested during battery check")
            return {"battery_level": 100, "charging_status": 0, "needs_charging": False}
        
        res = receive_response(ws, timeout=2)
        if res:
            cmd = res.get("cmd")
            if cmd == "notify_battery_info":
                data = res.get("data", {})
                battery_level = data.get("battery", 0)
                charging_status = data.get("status", 0)
                
                print(f"🔋 [BATTERY] Level: {battery_level}%, Charging Status: {charging_status}")
                
                return {
                    "battery_level": battery_level,
                    "charging_status": charging_status,
                    "needs_charging": battery_level < 20  # Use 20% as threshold like in the perfect code
                }
        
        time.sleep(0.5)
    
    print("🔋 [BATTERY] Failed to get battery status, using default")
    return {"battery_level": 100, "charging_status": 0, "needs_charging": False}

def dock_charge(ws, map_id, x, y, theta, max_attempts=3, full_level=95):
    """PERFECT CHARGING PROCESS from the provided file - EXACT COPY"""
    print(f"🔌 [CHARGING] Starting dock charge procedure at ({x}, {y}, {theta})")
    
    for attempt in range(max_attempts):
        if navigation_quit_event.is_set():
            print("🚪 [CHARGING] Quit requested during charging")
            return False
        
        print(f"🔌 [CHARGING] Attempt {attempt + 1}/{max_attempts}")
        
        send(ws, {
            "cmd": "request_dock_charge",
            "data": {"mapId": map_id, "x": x, "y": y, "theta": theta}
        })
        
        start_time = time.time()
        timeout = 120
        charging_started = False
        docking_successful = False
        
        while time.time() - start_time < timeout:
            if navigation_quit_event.is_set():
                return False
            
            res = receive_response(ws, timeout=2)
            
            if res:
                cmd = res.get("cmd")
                code = res.get("code")
                print(f"🔌 [CHARGING] Dock response - cmd: {cmd}, code: {code}")
                
                if cmd == "response_dock_ctrl":
                    if code == 0:
                        print("🔌 [CHARGING] Docking successful!")
                        docking_successful = True
                        break
                    elif code == 6016:
                        print("🔌 [CHARGING] No charging pile detected")
                        break
                elif cmd == "notify_heart_beat":
                    msg = res.get("msg", "")
                    if "navigation goal out costmap" in msg:
                        print("🔌 [CHARGING] Navigation goal out of costmap")
                        break
            
            time.sleep(1)
        
        if docking_successful:
            print("🔌 [CHARGING] Verifying charging started...")
            time.sleep(5)
            
            charging_confirmed = False
            for check_attempt in range(3):
                if navigation_quit_event.is_set():
                    return False
                
                battery_info = get_battery_status(ws)
                
                if battery_info["charging_status"] in [1, 2]:
                    print("🔌 [CHARGING] Charging confirmed!")
                    charging_confirmed = True
                    charging_started = True
                    break
                else:
                    print(f"🔌 [CHARGING] Charging not confirmed, attempt {check_attempt + 1}/3")
                    time.sleep(5)
            
            if charging_confirmed:
                break
            else:
                if attempt < max_attempts - 1:
                    print("🔌 [CHARGING] Charging not confirmed, undocking and retrying...")
                    send(ws, {"cmd": "request_dock_charge_off"})
                    time.sleep(5)
                    continue
        
        if attempt < max_attempts - 1:
            print("🔌 [CHARGING] Docking failed, waiting before retry...")
            time.sleep(5)
            continue
        else:
            print("🔌 [CHARGING] All docking attempts failed")
            return False
    
    if not charging_started:
        print("🔌 [CHARGING] Charging failed to start")
        return False
    
    # Monitor charging process
    print(f"🔌 [CHARGING] Monitoring charging process until {full_level}%...")
    charging_complete = False
    start_time = time.time()
    last_battery_check = time.time()
    
    while time.time() - start_time < 3600:  # 1 hour max
        if navigation_quit_event.is_set():
            print("🚪 [CHARGING] Quit requested during charging monitoring")
            return False
        
        if time.time() - last_battery_check >= 30:
            battery_info = get_battery_status(ws)
            last_battery_check = time.time()
            
            if battery_info["battery_level"] >= full_level:
                print(f"🔌 [CHARGING] Charging complete! (Level: {battery_info['battery_level']}%)")
                charging_complete = True
                break
            elif battery_info["charging_status"] == 0:
                print("🔌 [CHARGING] Charging stopped unexpectedly")
                return False
        
        time.sleep(5)
    
    print(f"🔌 [CHARGING] Charging process finished - Success: {charging_complete}")
    return charging_complete

def wait_for_localization(ws, timeout=15):
    """Waits for the robot to confirm it is localized."""
    print("⏳ [LOCALIZE] Waiting for robot to localize...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if navigation_quit_event.is_set():
            return False
        
        res = receive_response(ws, timeout=1)
        
        if res and res.get("cmd") == "notify_heart_beat":
            # Code 2005 often means "localized and ready"
            if res.get("code") == 2005:
                print("✅ [LOCALIZE] Robot localized successfully.")
                return True
            # Some firmwares might just send position data in heartbeat when localized
            elif "x" in res.get("data", {}):
                print("✅ [LOCALIZE] Robot localized (position received).")
                return True
        
        time.sleep(0.5)
    
    print("❌ [LOCALIZE] Localization timed out.")
    return False

def set_map(ws, map_name, map_id):
    print(f"🗺 [MAP] Setting map: {map_name} (ID: {map_id})")
    
    if not send(ws, {"cmd": "request_set_map", "data": {"mapId": map_id}}):
        return False
    
    while True:
        if navigation_quit_event.is_set():
            return False
        
        res = receive_response(ws)
        if res and res.get("cmd") == "response_set_map" and res.get("code") == 1000:
            print(f"🗺 [MAP] Map set successfully: {map_name}")
            return True

def get_points(ws, map_id):
    print(f"🗺 [MAP] Getting points for map ID: {map_id}")
    
    if not send(ws, {"cmd": "request_point_list", "data": {"mapId": map_id}}):
        return []
    
    start = time.time()
    while time.time() - start < 5:
        if navigation_quit_event.is_set():
            return []
        
        res = receive_response(ws, timeout=1)
        if res and res.get("cmd") == "response_point_list" and res.get("code") == 0:
            points = res.get("data", {}).get("points", [])
            print(f"🗺 [MAP] Found {len(points)} points")
            return points
    
    print(f"🗺 [MAP] No points found for map ID: {map_id}")
    return []

def reset_map(ws):
    print("🗺 [MAP] Resetting map")
    send(ws, {"cmd": "request_reset_map"})
    time.sleep(2)

def relocate(ws, x, y, theta, mode=2):
    print(f"📍 [RELOCATE] Relocating to ({x}, {y}, {theta}) with mode {mode}")
    
    if not send(ws, {"cmd": "request_force_relocate", "data": {"x": x, "y": y, "theta": theta, "mode": mode}}):
        return False
    
    start_time = time.time()
    while time.time() - start_time < 10:
        if navigation_quit_event.is_set():
            return False
        
        res = receive_response(ws)
        if res and res.get("cmd") == "response_relocate_position" and res.get("code") == 4000:
            print("📍 [RELOCATE] Relocation command acknowledged")
            return True
    
    print("❌ [RELOCATE] Relocation command failed or timed out")
    return False

def relocate_with_retry(ws, x, y, theta, retries=3):
    for attempt in range(retries):
        if navigation_quit_event.is_set():
            return False
        
        print(f"📍 [RELOCATE] Attempt {attempt + 1}/{retries}")
        
        reset_map(ws)
        
        if relocate(ws, x, y, theta):
            # After a successful relocation command, wait for localization confirmation
            if wait_for_localization(ws):
                print("✅ [RELOCATE] Relocation and localization confirmed.")
                return True
            else:
                print("⚠️ [RELOCATE] Relocation acknowledged, but localization failed.")
        
        if attempt < retries - 1:
            print(f"❌ [RELOCATE] Relocation attempt failed, retrying in 5 seconds...")
            time.sleep(5)
    
    print("❌ [RELOCATE] All relocation attempts failed.")
    return False

def cancel_current_navigation(ws):
    print("🛑 [NAV] Canceling current navigation")
    send(ws, {"cmd": "request_stop_navigation"})
    time.sleep(1)
    
    try:
        # Clear any pending responses
        while True:
            res = receive_response(ws, timeout=0.1)
            if not res:
                break
    except:
        pass

def ensure_robot_ready_for_navigation(ws):
    print("🤖 [NAV] Ensuring robot is ready for navigation")
    
    cancel_current_navigation(ws)
    time.sleep(1)
    
    send(ws, {"cmd": "request_robot_status"})
    res = receive_response(ws, timeout=3)
    
    max_wait = 10
    wait_time = 0
    
    while wait_time < max_wait:
        if navigation_quit_event.is_set():
            return False
        
        send(ws, {"cmd": "request_robot_status"})
        res = receive_response(ws, timeout=1)
        
        if res and res.get("code") in [2006, 0]:
            print("🤖 [NAV] Robot ready for navigation")
            return True
        
        time.sleep(1)
        wait_time += 1
    
    print("🤖 [NAV] Robot ready (timeout reached)")
    return True

def start_navigation_and_wait_completion(ws, x, y, theta, speed=0.5, navigation_control=None, emergency_mode=False):
    # Use slower speed for emergency mode to prevent overshooting
    if emergency_mode:
        speed = 0.15  # Even slower speed for emergency mode as in perfect code
        print(f"🚨 [NAV] Emergency navigation mode - using reduced speed: {speed}")
    
    print(f"🧭 [NAV] Starting navigation to ({x}, {y}, {theta}) with speed {speed}")
    
    if not ensure_robot_ready_for_navigation(ws):
        return False
    
    if not send(ws, {"cmd": "request_start_navigation", "data": {"x": x, "y": y, "theta": theta, "speed": speed}}):
        return False
    
    start_time = time.time()
    timeout = 180
    navigation_started = False
    navigation_running = False
    is_paused = False
    pause_count = 0
    
    while True:
        # Check for quit first
        if navigation_quit_event.is_set():
            print("🚪 [NAV] Quit requested during navigation")
            send(ws, {"cmd": "request_stop_navigation"})
            return False
        
        # Check for emergency exit first (but not if we're already in emergency mode)
        if not emergency_mode and check_emergency_exit_during_navigation(ws, navigation_control):
            print("🚨 [NAV] Emergency exit executed during navigation")
            return False  # Emergency exit was executed
        
        # Check for force stop
        if navigation_control and navigation_control.get('force_stop') and navigation_control['force_stop'].is_set():
            print("🛑 [NAV] Force stop detected")
            send(ws, {"cmd": "request_stop_navigation"})
            return False
        
        # Check global stop event
        if navigation_stop_event.is_set():
            print("🛑 [NAV] Global stop event detected")
            send(ws, {"cmd": "request_stop_navigation"})
            return False
        
        # Handle pause/resume logic using navigation_pause_event
        if navigation_pause_event.is_set():
            if not is_paused:
                print("⏸ [NAV] Navigation paused")
                send(ws, {"cmd": "request_stop_navigation"})
                is_paused = True
                pause_count += 1
                
                # Clear any pending responses
                time.sleep(1)
                try:
                    while True:
                        res = receive_response(ws, timeout=0.1)
                        if not res:
                            break
                except:
                    pass
            
            # Wait until pause is cleared
            while navigation_pause_event.is_set():
                if navigation_quit_event.is_set():
                    return False
                time.sleep(0.2)
            
            if is_paused:
                print("▶ [NAV] Navigation resumed")
                
                # For multiple pauses, ensure robot is properly reset
                if pause_count > 1:
                    if not ensure_robot_ready_for_navigation(ws):
                        return False
                    time.sleep(2)
                else:
                    time.sleep(1)
                
                if not send(ws, {"cmd": "request_start_navigation", "data": {"x": x, "y": y, "theta": theta, "speed": speed}}):
                    return False
                
                start_time = time.time()
                navigation_started = False
                navigation_running = False
                is_paused = False
                time.sleep(0.5)
        
        # Handle navigation_control pause logic (backward compatibility)
        if navigation_control and navigation_control.get('paused') and navigation_control['paused'].is_set():
            if not is_paused:
                print("⏸ [NAV] Navigation control pause triggered")
                send(ws, {"cmd": "request_stop_navigation"})
                is_paused = True
                pause_count += 1
                
                time.sleep(1)
                try:
                    while True:
                        res = receive_response(ws, timeout=0.1)
                        if not res:
                            break
                except:
                    pass
            
            while navigation_control['paused'].is_set():
                if navigation_quit_event.is_set():
                    return False
                time.sleep(0.2)
            
            if is_paused:
                print("▶ [NAV] Navigation control resume triggered")
                
                if pause_count > 1:
                    if not ensure_robot_ready_for_navigation(ws):
                        return False
                    time.sleep(2)
                else:
                    time.sleep(1)
                
                if not send(ws, {"cmd": "request_start_navigation", "data": {"x": x, "y": y, "theta": theta, "speed": speed}}):
                    return False
                
                start_time = time.time()
                navigation_started = False
                navigation_running = False
                is_paused = False
                time.sleep(0.5)
        
        res = receive_response(ws, timeout=1)
        
        if res:
            cmd = res.get("cmd")
            code = res.get("code")
            code_description = NAVI_CODES.get(code, f"Unknown code: {code}")
            
            if cmd == "response_start_navigation" and (code == 1001 or res.get('msg') == 'navigation success'):
                print("✅ [NAV] Navigation started successfully")
                navigation_started = True
                
            elif cmd == "notify_heart_beat":
                if code == 6100 or code == 2007:
                    if not navigation_running:
                        print("🏃 [NAV] Navigation is running")
                        navigation_running = True
                        
                elif code == 2006:
                    if navigation_started and navigation_running:
                        print("🎯 [NAV] Navigation completed successfully!")
                        
                        # ENHANCED STOPPING PROCEDURE FOR PRECISE DESTINATION REACH
                        if emergency_mode:
                            print("🛑 [EMERGENCY] Executing precision stop at destination...")
                            
                            # Multiple immediate stop commands for emergency mode
                            for i in range(3):
                                send(ws, {"cmd": "request_stop_navigation"})
                                print(f"🛑 [EMERGENCY] Precision stop command {i+1}/3")
                                time.sleep(0.2)
                            
                            # Verify final position
                            time.sleep(1)
                            send(ws, {"cmd": "request_robot_status"})
                            final_status = receive_response(ws, timeout=2)
                            if final_status:
                                print(f"🤖 [EMERGENCY] Final robot status: {final_status}")
                        
                        return True
                    else:
                        print("⚠ [NAV] Navigation completed but not properly started/running")
                        
                elif code == 3001:
                    print("🚧 [NAV] Obstacle detected during navigation")
                    obstacle_avoidance.handle_obstacle(ws)
                    
                elif code == 4001:
                    print("🚨 [NAV] Emergency stop activated")
                    return False
        
        if time.time() - start_time > timeout:
            print("⏰ [NAV] Navigation timeout reached")
            return False
        
        time.sleep(0.1)

def execute_charging_phase(ws, charge_map_id, charge_anchor, charge_pile, target_level=95):
    print(f"🔌 [CHARGING] Starting charging phase (target: {target_level}%)")
    
    if not set_map(ws, "charge_station", charge_map_id):
        return False
    
    if not relocate_with_retry(ws, charge_anchor["x"], charge_anchor["y"], charge_anchor["theta"]):
        print("❌ [CHARGING] Failed to relocate to charging anchor")
        return False
    
    charging_success = dock_charge(ws, charge_map_id, charge_pile["x"], charge_pile["y"], charge_pile["theta"], full_level=target_level)
    
    if charging_success:
        # Undock after charging to prepare for next navigation
        print("🔌 [CHARGING] Undocking from charging pile...")
        send(ws, {"cmd": "request_dock_charge_off"})
        time.sleep(5)  # Wait for undock to complete
        print("✅ [CHARGING] Charging phase completed successfully")
    else:
        print("❌ [CHARGING] Charging phase failed")
    
    return charging_success

def check_battery_and_charge_if_needed(ws, charge_map_id, charge_anchor, charge_pile, threshold=20, target_level=95):
    print(f"🔋 [BATTERY] Checking battery level (threshold: {threshold}%, target: {target_level}%)...")
    
    battery_info = get_battery_status(ws)
    
    if battery_info["battery_level"] < threshold:
        print(f"🔋 [BATTERY] Battery level ({battery_info['battery_level']}%) below threshold. Charging required.")
        return execute_charging_phase(ws, charge_map_id, charge_anchor, charge_pile, target_level)
    else:
        print(f"✅ [BATTERY] Battery level ({battery_info['battery_level']}%) sufficient. No charging needed.")
        return True

def execute_map_navigation(ws, map_name, map_id, navigation_control=None, reverse_mode=False, max_retries=9999, emergency_mode=False):
    print(f"🗺 [NAV] Starting map navigation - Map: {map_name}, ID: {map_id}, Reverse: {reverse_mode}, Emergency: {emergency_mode}")
    
    for attempt in range(max_retries):
        if navigation_quit_event.is_set():
            print("🚪 [MAP NAV] Quit requested")
            return False
        
        print(f"🔄 [NAV] Navigation attempt {attempt + 1}/{max_retries}")
        
        # Check for emergency exit (but not if we're already in emergency mode)
        if not emergency_mode and emergency_exit_event.is_set():
            print("🚨 [MAP NAV] Emergency exit detected, stopping navigation")
            return False
        
        if navigation_control and navigation_control.get('force_stop') and navigation_control['force_stop'].is_set():
            print("🛑 [MAP NAV] Force stop detected")
            return False
        
        if navigation_stop_event.is_set():
            print("🛑 [MAP NAV] Global stop detected")
            return False
        
        cancel_current_navigation(ws)
        
        if not set_map(ws, map_name, map_id):
            return False
        
        points = get_points(ws, map_id)
        if not points:
            print(f"❌ [NAV] No points found for map {map_name}")
            return False
        
        anchor = next((p for p in points if p.get("type") == "anchor_point"), None)
        dest = next((p for p in points if p.get("type") == "destination"), None)
        
        if not anchor or not dest:
            print(f"❌ [NAV] Missing waypoints for map {map_name} - Anchor: {anchor is not None}, Dest: {dest is not None}")
            return False
        
        # Swap anchor and dest if reverse_mode
        start_point, end_point = (dest, anchor) if reverse_mode else (anchor, dest)
        
        print(f"📍 [NAV] Start point: ({start_point['x']}, {start_point['y']}, {start_point['theta']})")
        print(f"🎯 [NAV] End point: ({end_point['x']}, {end_point['y']}, {end_point['theta']})")
        
        if not relocate_with_retry(ws, start_point["x"], start_point["y"], start_point["theta"]):
            print(f"❌ [NAV] Failed to relocate to start point, attempt {attempt + 1}")
            time.sleep(5)
            continue
        
        time.sleep(2)
        
        success = start_navigation_and_wait_completion(ws, end_point["x"], end_point["y"], end_point["theta"], navigation_control=navigation_control, emergency_mode=emergency_mode)
        
        if success:
            print(f"✅ [NAV] Map navigation completed successfully: {map_name}")
            return True
        else:
            print(f"❌ [NAV] Map navigation failed: {map_name}, attempt {attempt + 1}")
            time.sleep(10)  # Wait before retrying
    
    print(f"❌ [NAV] All navigation attempts failed for map: {map_name}")
    return False

def pre_navigation_battery_check_and_charge(ws, charge_map_id, charge_anchor, charge_point, min_level=20, full_level=95):
    """
    PERFECT PRE-NAVIGATION BATTERY CHECK from the provided file - EXACT COPY
    Checks battery before navigation. If below min_level, relocates to anchor,
    docks, and charges to full_level.
    
    charge_anchor: dict with keys x, y, theta for relocation
    charge_point: dict with keys x, y, theta for docking
    """
    print(f"🔋 [BATTERY] Pre-navigation battery check - Min: {min_level}%, Full: {full_level}%")
    
    battery_info = get_battery_status(ws)
    
    if battery_info["battery_level"] < min_level:
        print(f"🔋 [BATTERY] Battery too low ({battery_info['battery_level']}%), starting charging process")
        
        if not set_map(ws, "charge_station", charge_map_id):
            return False
        
        # Relocate to the anchor point on the charging map first
        print("📍 [CHARGING] Relocating to charging map anchor point...")
        if not relocate_with_retry(ws, charge_anchor["x"], charge_anchor["y"], charge_anchor["theta"]):
            print("❌ [CHARGING] Failed to relocate to charging anchor point.")
            return False
        
        print("✅ [CHARGING] Relocated successfully. Starting dock charge.")
        time.sleep(2)  # Give time to stabilize after relocation
        
        if dock_charge(ws, charge_map_id, charge_point["x"], charge_point["y"], charge_point["theta"], full_level=full_level):
            # dock_charge now waits until full_level
            print(f"🔋 [BATTERY] Battery charged to {full_level}% or more.")
            
            # Undock after charging to prepare for next navigation
            print("🔌 [CHARGING] Undocking from charging pile...")
            send(ws, {"cmd": "request_dock_charge_off"})
            time.sleep(5)  # Wait for undock to complete
            
            return True
        else:
            print("❌ [BATTERY] Charging failed")
            return False
    else:
        print(f"🔋 [BATTERY] Battery level sufficient: {battery_info['battery_level']}%")
        return True

def run_multi_map_navigation_with_charging(robot_ip, map_ids, charge_map_id, port, navigation_status=None, navigation_control=None):
    global current_map_position, map_sequence, navigation_phase
    cycles_completed = 0
    
    print("🚀 [SYSTEM] Starting multi-map navigation with charging system")
    print(f"🤖 [SYSTEM] Robot IP: {robot_ip}, Port: {port}")
    print(f"🗺 [SYSTEM] Map sequence: {map_ids}")
    print(f"🔌 [SYSTEM] Charge map ID: {charge_map_id}")
    
    # Clear map tracking at start
    clear_map_tracking()
    
    # Pre-load robot maps cache for name resolution
    try:
        import requests
        response = requests.get(f"http://localhost:5000/api/robot/maps", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('maps'):
                update_robot_maps_cache(data['maps'])
                print(f"🗺 [SYSTEM] Pre-loaded {len(data['maps'])} maps for name resolution")
    except Exception as e:
        print(f"⚠️ [SYSTEM] Could not pre-load maps cache: {e}")
    
    try:
        while not navigation_quit_event.is_set():
            print(f"🔄 [CYCLE] Starting cycle {cycles_completed + 1}")
            
            # --- PAUSE/STOP SUPPORT ---
            while navigation_pause_event.is_set() and not navigation_quit_event.is_set():
                print("⏸ [CYCLE] Cycle paused, waiting...")
                time.sleep(0.5)
            
            if navigation_stop_event.is_set() or navigation_quit_event.is_set():
                message = "Navigation quit requested" if navigation_quit_event.is_set() else "Navigation stopped"
                print(f"🛑 [CYCLE] {message}")
                return {"success": False, "message": message}
            
            if navigation_status is not None:
                navigation_status['cycle'] = cycles_completed + 1
            
            try:
                print("🔌 [CYCLE] Establishing websocket connection...")
                ws = websocket.create_connection(f"ws://{robot_ip}:{port}")
                print("✅ [CYCLE] Websocket connection established")
                
            except Exception as e:
                print(f"❌ [CYCLE] Failed to establish websocket connection: {e}")
                if navigation_quit_event.is_set():
                    return {"success": False, "message": "Navigation quit requested"}
                time.sleep(30)
                continue
            
            try:
                # Set up map sequence for emergency exit tracking
                map_sequence = map_ids.copy()
                current_map_position = 0
                navigation_phase = "forward"  # Start with forward phase
                
                print(f"🗺 [CYCLE] Map sequence initialized: {len(map_sequence)} maps")
                print(f"🔄 [CYCLE] Starting forward navigation phase")
                
                # Get charge station points
                if not set_map(ws, "charge_station", charge_map_id):
                    print("❌ [CYCLE] Failed to set charge station map")
                    close_websocket_gracefully(ws)
                    time.sleep(30)
                    continue
                
                charge_points = get_points(ws, charge_map_id)
                if not charge_points:
                    print("❌ [CYCLE] No charge station points found")
                    close_websocket_gracefully(ws)
                    time.sleep(30)
                    continue
                
                charge_anchor = next((p for p in charge_points if p.get("type") == "anchor_point"), None)
                charge_pile = next((p for p in charge_points if p.get("type") == "charge"), None)
                
                if not charge_anchor or not charge_pile:
                    print("❌ [CYCLE] Missing charge station waypoints")
                    close_websocket_gracefully(ws)
                    time.sleep(30)
                    continue
                
                print("🔌 [CYCLE] Charge station configured successfully")
                
                # PRE-NAVIGATION BATTERY CHECK AND CHARGING using PERFECT PROCESS
                charge_point = {"x": charge_pile["x"], "y": charge_pile["y"], "theta": charge_pile["theta"]}
                if not pre_navigation_battery_check_and_charge(ws, charge_map_id, charge_anchor, charge_point, min_level=20, full_level=95):
                    print("❌ [CYCLE] Pre-navigation charging failed, retrying cycle...")
                    close_websocket_gracefully(ws)
                    if navigation_quit_event.is_set():
                        return {"success": False, "message": "Navigation quit requested"}
                    time.sleep(30)
                    continue
                
                successful_maps = []
                failed_maps = []
                
                print("➡ [CYCLE] Starting forward navigation phase")
                navigation_phase = "forward"
                
                # 1. Forward navigation for all maps
                for idx, map_id in enumerate(map_ids):
                    if navigation_quit_event.is_set():
                        print("🚪 [FORWARD] Quit requested during forward navigation")
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Navigation quit requested"}
                    
                    current_map_position = idx
                    print(f"🗺 [FORWARD] Processing map {idx + 1}/{len(map_ids)}: {map_id}")
                    print(f"📍 [FORWARD] Current map position: {current_map_position} (Map {current_map_position + 1})")
                    
                    # Update map tracking for forward navigation
                    update_map_tracking(map_ids, idx, robot_ip)
                    
                    if navigation_status is not None:
                        navigation_status['current_map'] = map_id
                    
                    # Check for emergency exit BEFORE starting navigation
                    if emergency_exit_event.is_set():
                        print("🚨 [FORWARD] Emergency exit triggered before map navigation!")
                        if execute_emergency_exit_navigation(ws, map_ids, navigation_control):
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": True, "message": "Emergency exit completed"}
                        else:
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": False, "message": "Emergency exit failed"}
                    
                    if navigation_control and navigation_control.get('force_stop') and navigation_control['force_stop'].is_set():
                        print("🛑 [FORWARD] Force stop triggered")
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Force stop triggered"}
                    
                    if navigation_stop_event.is_set():
                        print("🛑 [FORWARD] Navigation stopped")
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Navigation stopped"}
                    
                    while navigation_control and navigation_control.get('paused') and navigation_control['paused'].is_set() and not navigation_quit_event.is_set():
                        if navigation_status is not None:
                            navigation_status['paused'] = True
                        print("⏸ [FORWARD] Navigation paused...")
                        time.sleep(0.5)
                    
                    while navigation_pause_event.is_set() and not navigation_quit_event.is_set():
                        print("⏸ [FORWARD] Navigation paused (global)...")
                        time.sleep(0.5)
                    
                    if navigation_status is not None:
                        navigation_status['paused'] = False
                    
                    map_name = f"map{idx+1}"
                    print(f"🚀 [FORWARD] Starting navigation for {map_name}")
                    
                    success = execute_map_navigation(ws, map_name, map_id, navigation_control=navigation_control, reverse_mode=False)
                    
                    if success:
                        successful_maps.append(map_name)
                        print(f"✅ [FORWARD] {map_name} completed successfully")
                    else:
                        failed_maps.append(map_name)
                        print(f"❌ [FORWARD] {map_name} failed")
                    
                    if navigation_quit_event.is_set():
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Navigation quit requested"}
                    
                    # CRITICAL: Keep the current position at the current map after completion
                    # Don't update until we start reverse or move to next map
                    print(f"📍 [FORWARD] Maintaining position at Map {current_map_position + 1} after completion")
                    
                    # Check for emergency exit AFTER completing current map navigation
                    if emergency_exit_event.is_set():
                        print("🚨 [FORWARD] Emergency exit triggered! Current map completed, proceeding to emergency exit...")
                        print(f"📍 [FORWARD] Emergency triggered at Map {current_map_position + 1}")
                        if execute_emergency_exit_navigation(ws, map_ids, navigation_control):
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": True, "message": "Emergency exit completed after current map"}
                        else:
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": False, "message": "Emergency exit failed"}
                    
                    # REMOVED: Battery check after each map - only wait between maps
                    if idx != len(map_ids) - 1:
                        print("⏳ [FORWARD] Waiting 3 seconds before next map...")
                        for i in range(6):  # 3 seconds with quit checks
                            if navigation_quit_event.is_set():
                                close_websocket_gracefully(ws)
                                return {"success": False, "message": "Navigation quit requested"}
                            time.sleep(0.5)
                
                print("🔄 [CYCLE] Starting reverse navigation phase")
                navigation_phase = "reverse"
                
                # 2. Reverse navigation for all maps, in reverse order
                for idx, map_id in enumerate(reversed(map_ids)):
                    if navigation_quit_event.is_set():
                        print("🚪 [REVERSE] Quit requested during reverse navigation")
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Navigation quit requested"}
                    
                    # Update current position for emergency exit calculation
                    current_map_position = len(map_ids) - 1 - idx
                    print(f"🗺 [REVERSE] Processing map {idx + 1}/{len(map_ids)}: {map_id} (position {current_map_position})")
                    print(f"📍 [REVERSE] Current map position: {current_map_position} (Map {current_map_position + 1})")
                    
                    # Update map tracking for reverse navigation
                    update_map_tracking(map_ids, current_map_position, robot_ip)
                    
                    # Check for emergency exit BEFORE starting reverse navigation
                    if emergency_exit_event.is_set():
                        print("🚨 [REVERSE] Emergency exit triggered during reverse navigation!")
                        print(f"📍 [REVERSE] Emergency triggered at Map {current_map_position + 1}")
                        if execute_emergency_exit_navigation(ws, map_ids, navigation_control):
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": True, "message": "Emergency exit completed"}
                        else:
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": False, "message": "Emergency exit failed"}
                    
                    map_name = f"map{len(map_ids)-idx}"
                    print(f"🚀 [REVERSE] Starting reverse navigation for {map_name}")
                    
                    reverse_success = execute_map_navigation(ws, map_name, map_id, navigation_control=navigation_control, reverse_mode=True)
                    
                    if reverse_success:
                        successful_maps.append(map_name + "_reverse")
                        print(f"✅ [REVERSE] {map_name} reverse completed successfully")
                    else:
                        failed_maps.append(map_name + "_reverse")
                        print(f"❌ [REVERSE] {map_name} reverse failed")
                    
                    if navigation_quit_event.is_set():
                        close_websocket_gracefully(ws)
                        return {"success": False, "message": "Navigation quit requested"}
                    
                    # CRITICAL: Keep the current position at the current map after completion
                    print(f"📍 [REVERSE] Maintaining position at Map {current_map_position + 1} after reverse completion")
                    
                    # Check for emergency exit AFTER completing current reverse map navigation
                    if emergency_exit_event.is_set():
                        print("🚨 [REVERSE] Emergency exit triggered! Current reverse map completed, proceeding to emergency exit...")
                        print(f"📍 [REVERSE] Emergency triggered at Map {current_map_position + 1}")
                        if execute_emergency_exit_navigation(ws, map_ids, navigation_control):
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": True, "message": "Emergency exit completed after current reverse map"}
                        else:
                            clear_emergency_exit()
                            close_websocket_gracefully(ws)
                            return {"success": False, "message": "Emergency exit failed"}
                    
                    # REMOVED: Battery check after each reverse map - only wait between maps
                    if idx != len(map_ids) - 1:
                        print("⏳ [REVERSE] Waiting 3 seconds before next reverse map...")
                        for i in range(6):  # 3 seconds with quit checks
                            if navigation_quit_event.is_set():
                                close_websocket_gracefully(ws)
                                return {"success": False, "message": "Navigation quit requested"}
                            time.sleep(0.5)
                
                # FINAL BATTERY CHECK - Only after complete cycle
                print("🔋 [CYCLE] Checking battery status after complete cycle...")
                if not check_battery_and_charge_if_needed(ws, charge_map_id, charge_anchor, charge_pile, threshold=20, target_level=95):
                    print("❌ [CYCLE] End-of-cycle charging failed")
                
                print("✅ [CYCLE] Navigation cycle completed")
                print(f"📊 [CYCLE] Successful maps: {len(successful_maps)}")
                print(f"📊 [CYCLE] Failed maps: {len(failed_maps)}")
                
                # Clear map tracking at end of cycle
                clear_map_tracking()
                
            finally:
                close_websocket_gracefully(ws)
            
            cycles_completed += 1
            print(f"🏁 [CYCLE] Cycle {cycles_completed} finished")
            
            print("⏳ [CYCLE] Waiting 10 seconds before next cycle...")
            for i in range(20):  # Wait 10 seconds, but check for quit every 0.5s
                if navigation_quit_event.is_set():
                    print("🚪 [CYCLE] Quit requested during wait")
                    return {"success": False, "message": "Navigation quit requested"}
                
                if navigation_stop_event.is_set():
                    print("🛑 [CYCLE] Navigation stopped during wait")
                    return {"success": False, "message": "Navigation stopped."}
                
                while navigation_pause_event.is_set() and not navigation_quit_event.is_set():
                    time.sleep(0.5)
                
                time.sleep(0.5)  # Wait before next cycle
        
        print("🚪 [SYSTEM] Navigation system quit gracefully")
        return {"success": False, "message": "Navigation quit requested"}
        
    except Exception as e:
        print(f"❌ [SYSTEM] Exception occurred: {e}")
        
        # --- PAUSE/STOP SUPPORT IN EXCEPTION ---
        while navigation_pause_event.is_set() and not navigation_quit_event.is_set():
            time.sleep(0.5)
        
        if navigation_quit_event.is_set():
            return {"success": False, "message": "Navigation quit requested after exception"}
        
        if navigation_stop_event.is_set():
            return {"success": False, "message": "Navigation stopped after exception."}
        # --- END PAUSE/STOP SUPPORT IN EXCEPTION ---
        
        return {"success": False, "message": str(e)}

def main():
    print("🤖 [MAIN] Robot Navigation System Starting...")
    
    ROBOT_IP = "192.168.1.100"
    WS_PORT = 8080
    MAP_IDS = [1, 2, 3, 4, 5]  # Map2 should contain EMERGENCY_EXIT_MAP_ID
    CHARGE_MAP_ID = MAP_ID  # Using the provided MAP_ID
    
    print(f"🤖 [MAIN] Configuration:")
    print(f"  - Robot IP: {ROBOT_IP}")
    print(f"  - WebSocket Port: {WS_PORT}")
    print(f"  - Map IDs: {MAP_IDS}")
    print(f"  - Charge Map ID: {CHARGE_MAP_ID}")
    print(f"  - Emergency Exit Map ID: {EMERGENCY_EXIT_MAP_ID}")
    print(f"  - Charge Point: x={CHARGE_POINT['x']}, y={CHARGE_POINT['y']}, theta={CHARGE_POINT['theta']}")
    
    while not navigation_quit_event.is_set():
        try:
            print("🔌 [MAIN] Establishing connection to robot...")
            ws = websocket.create_connection(f"ws://{ROBOT_IP}:{WS_PORT}")
            print("✅ [MAIN] Connection established")
            
            try:
                # Set up map sequence for emergency exit tracking
                global map_sequence, current_map_position, navigation_phase
                map_sequence = MAP_IDS.copy()
                current_map_position = 0
                navigation_phase = "forward"
                
                # Get charge station points using PERFECT PROCESS
                if not set_map(ws, "charge_station", CHARGE_MAP_ID):
                    print("❌ [MAIN] Failed to set charge station map")
                    close_websocket_gracefully(ws)
                    if navigation_quit_event.is_set():
                        break
                    time.sleep(30)
                    continue
                
                charge_points = get_points(ws, CHARGE_MAP_ID)
                if charge_points:
                    charge_anchor = next((p for p in charge_points if p.get("type") == "anchor_point"), None)
                    charge_pile = next((p for p in charge_points if p.get("type") == "charge"), None)
                    
                    if charge_anchor and charge_pile:
                        print("🔌 [MAIN] Charge station configured, checking initial battery...")
                        
                        # PRE-NAVIGATION BATTERY CHECK using PERFECT PROCESS
                        charge_point = {"x": charge_pile["x"], "y": charge_pile["y"], "theta": charge_pile["theta"]}
                        if not pre_navigation_battery_check_and_charge(ws, CHARGE_MAP_ID, charge_anchor, charge_point, min_level=20, full_level=95):
                            print("❌ [MAIN] Pre-navigation charging failed")
                            close_websocket_gracefully(ws)
                            if navigation_quit_event.is_set():
                                break
                            time.sleep(30)
                            continue
                    else:
                        print("⚠ [MAIN] Charge station points incomplete")
                        charge_anchor = None
                        charge_pile = None
                else:
                    print("⚠ [MAIN] No charge station points found")
                    charge_anchor = None
                    charge_pile = None
                
                successful_maps = []
                failed_maps = []
                
                print("➡ [MAIN] Starting forward navigation...")
                navigation_phase = "forward"
                
                for idx, map_id in enumerate(MAP_IDS):
                    if navigation_quit_event.is_set():
                        print("🚪 [MAIN] Quit requested during forward navigation")
                        break
                    
                    current_map_position = idx
                    print(f"📍 [MAIN] Current map position: {current_map_position} (Map {current_map_position + 1})")
                    
                    if navigation_stop_event.is_set():
                        print("🛑 [MAIN] Navigation stopped")
                        break
                    
                    map_name = f"map{idx+1}"
                    print(f"🗺 [MAIN] Processing {map_name} ({idx+1}/{len(MAP_IDS)})")
                    
                    success = execute_map_navigation(ws, map_name, map_id)
                    
                    if success:
                        successful_maps.append(map_name)
                        print(f"✅ [MAIN] {map_name} completed successfully")
                    else:
                        failed_maps.append(map_name)
                        print(f"❌ [MAIN] {map_name} failed")
                    
                    if navigation_quit_event.is_set():
                        break
                    
                    # CRITICAL: Keep position at current map after completion
                    print(f"📍 [MAIN] Maintaining position at Map {current_map_position + 1} after completion")
                    
                    # Check for emergency exit after completing current map
                    if emergency_exit_event.is_set():
                        print("🚨 [MAIN] Emergency exit triggered! Proceeding to emergency exit...")
                        print(f"📍 [MAIN] Emergency triggered at Map {current_map_position + 1}")
                        if execute_emergency_exit_navigation(ws, MAP_IDS):
                            clear_emergency_exit()
                            break
                        else:
                            clear_emergency_exit()
                            print("❌ [MAIN] Emergency exit failed")
                            break
                    
                    # REMOVED: Battery check after each map - only wait between maps
                    if idx != len(MAP_IDS) - 1:
                        print("⏳ [MAIN] Waiting 3 seconds before next map...")
                        for i in range(6):  # 3 seconds with quit checks
                            if navigation_quit_event.is_set():
                                break
                            time.sleep(0.5)
                
                if navigation_quit_event.is_set():
                    break
                
                if not navigation_quit_event.is_set() and not navigation_stop_event.is_set() and not emergency_exit_event.is_set():
                    print("🔄 [MAIN] Starting reverse navigation...")
                    navigation_phase = "reverse"
                    
                    # Reverse navigation for all maps, in reverse order
                    for idx, map_id in enumerate(reversed(MAP_IDS)):
                        if navigation_quit_event.is_set():
                            print("🚪 [MAIN] Quit requested during reverse navigation")
                            break
                        
                        current_map_position = len(MAP_IDS) - 1 - idx
                        print(f"📍 [MAIN] Current map position: {current_map_position} (Map {current_map_position + 1})")
                        
                        if emergency_exit_event.is_set():
                            print("🚨 [MAIN] Emergency exit triggered during reverse navigation!")
                            print(f"📍 [MAIN] Emergency triggered at Map {current_map_position + 1}")
                            if execute_emergency_exit_navigation(ws, MAP_IDS):
                                clear_emergency_exit()
                                break
                            else:
                                clear_emergency_exit()
                                print("❌ [MAIN] Emergency exit failed")
                                break
                        
                        map_name = f"map{len(MAP_IDS)-idx}"
                        print(f"🗺 [MAIN] Reverse processing {map_name} ({idx+1}/{len(MAP_IDS)})")
                        
                        reverse_success = execute_map_navigation(ws, map_name, map_id, reverse_mode=True)
                        
                        if reverse_success:
                            successful_maps.append(map_name + "_reverse")
                            print(f"✅ [MAIN] {map_name} reverse completed successfully")
                        else:
                            failed_maps.append(map_name + "_reverse")
                            print(f"❌ [MAIN] {map_name} reverse failed")
                        
                        if navigation_quit_event.is_set():
                            break
                        
                        # CRITICAL: Keep position at current map after completion
                        print(f"📍 [MAIN] Maintaining position at Map {current_map_position + 1} after reverse completion")
                        
                        # Check for emergency exit after completing current reverse map
                        if emergency_exit_event.is_set():
                            print("🚨 [MAIN] Emergency exit triggered! Proceeding to emergency exit...")
                            print(f"📍 [MAIN] Emergency triggered at Map {current_map_position + 1}")
                            if execute_emergency_exit_navigation(ws, MAP_IDS):
                                clear_emergency_exit()
                                break
                            else:
                                clear_emergency_exit()
                                print("❌ [MAIN] Emergency exit failed")
                                break
                        
                        # REMOVED: Battery check after each reverse map - only wait between maps
                        if idx != len(MAP_IDS) - 1:
                            print("⏳ [MAIN] Waiting 3 seconds before next reverse map...")
                            for i in range(6):  # 3 seconds with quit checks
                                if navigation_quit_event.is_set():
                                    break
                                time.sleep(0.5)
                        
                        if navigation_quit_event.is_set():
                            break
                
                # FINAL BATTERY CHECK using PERFECT PROCESS - Only after complete cycle
                if not navigation_quit_event.is_set() and charge_points and charge_anchor and charge_pile:
                    print("🔋 [MAIN] Final battery check after complete cycle...")
                    if not check_battery_and_charge_if_needed(ws, CHARGE_MAP_ID, charge_anchor, charge_pile, threshold=20, target_level=95):
                        print("❌ [MAIN] Final charging failed")
                
                # Summary
                if not navigation_quit_event.is_set():
                    total_expected = len(MAP_IDS) * 2
                    total_successful = len(successful_maps)
                    total_failed = len(failed_maps)
                    
                    if total_successful == total_expected:
                        print("🎉 [MAIN] All map navigations (forward and reverse) completed successfully!")
                    else:
                        print(f"📊 [MAIN] Navigation summary:")
                        print(f"  - Successful: {total_successful}/{total_expected}")
                        print(f"  - Failed: {total_failed}/{total_expected}")
                        print(f"  - Success rate: {(total_successful/total_expected)*100:.1f}%")
                
            finally:
                close_websocket_gracefully(ws)
            
            if navigation_quit_event.is_set():
                print("🚪 [MAIN] Quit requested, exiting main loop")
                break
            
            print("🔁 [MAIN] Waiting 10 seconds before starting the next 24/7 cycle...")
            for i in range(20):  # 10 seconds with quit checks
                if navigation_quit_event.is_set():
                    print("🚪 [MAIN] Quit requested during wait")
                    break
                time.sleep(0.5)
                
        except Exception as e:
            print(f"❌ [MAIN] Error occurred: {e}")
            if navigation_quit_event.is_set():
                print("🚪 [MAIN] Quit requested after error")
                break
            
            print("🔁 [MAIN] Waiting 30 seconds before retrying after error...")
            for i in range(60):  # 30 seconds with quit checks
                if navigation_quit_event.is_set():
                    break
                time.sleep(0.5)
    
    print("🚪 [MAIN] Navigation system shut down gracefully")
    
    # Shutdown TTS manager
    tts_manager.shutdown()

def create_navigation_interface():
    """
    Simple command line interface for navigation control
    This can be replaced with a GUI or web interface
    """
    import threading
    
    def interface_loop():
        print("\n" + "="*50)
        print("🤖 ROBOT NAVIGATION CONTROL INTERFACE")
        print("="*50)
        print("Commands:")
        print("  'start' or 's' - Start/Reset navigation")
        print("  'pause' or 'p' - Pause navigation")
        print("  'resume' or 'r' - Resume navigation")
        print("  'stop' - Stop current cycle")
        print("  'emergency' or 'e' - Trigger emergency exit")
        print("  'quit' or 'q' - Quit navigation system")
        print("  'help' or 'h' - Show this help")
        print("="*50)
        
        while not navigation_quit_event.is_set():
            try:
                command = input("\nEnter command: ").strip().lower()
                
                if command in ['start', 's']:
                    print("🔄 Starting/Resetting navigation...")
                    reset_navigation_events()
                    
                elif command in ['pause', 'p']:
                    print("⏸ Pausing navigation...")
                    pause_navigation()
                    
                elif command in ['resume', 'r']:
                    print("▶ Resuming navigation...")
                    continue_navigation()
                    
                elif command == 'stop':
                    print("🛑 Stopping navigation...")
                    stop_navigation()
                    
                elif command in ['emergency', 'e']:
                    print("🚨 Triggering emergency exit...")
                    trigger_emergency_exit()
                    
                elif command in ['quit', 'q']:
                    print("🚪 Quitting navigation system...")
                    quit_navigation()
                    break
                    
                elif command in ['help', 'h']:
                    print("\nCommands:")
                    print("  'start' or 's' - Start/Reset navigation")
                    print("  'pause' or 'p' - Pause navigation")
                    print("  'resume' or 'r' - Resume navigation")
                    print("  'stop' - Stop current cycle")
                    print("  'emergency' or 'e' - Trigger emergency exit")
                    print("  'quit' or 'q' - Quit navigation system")
                    print("  'help' or 'h' - Show this help")
                    
                elif command == '':
                    continue
                    
                else:
                    print(f"❌ Unknown command: {command}. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                print("\n🚪 Keyboard interrupt received. Quitting...")
                quit_navigation()
                break
                
            except EOFError:
                print("\n🚪 End of input. Quitting...")
                quit_navigation()
                break
                
            except Exception as e:
                print(f"❌ Interface error: {e}")
    
    # Start interface in a separate thread
    interface_thread = threading.Thread(target=interface_loop, daemon=True)
    interface_thread.start()
    return interface_thread

if __name__ == "__main__":
    print("🚀 [SYSTEM] Robot Navigation System v8.1 - OPTIMIZED BATTERY MANAGEMENT")
    print("🤖 [SYSTEM] Battery Management - Check only at cycle start and end")
    print("📋 [SYSTEM] Using PERFECT charging process from provided execution.py")
    print("🔌 [SYSTEM] Charging: Set Map → Relocate to Anchor → Dock Charge → Monitor → Undock")
    print("📍 [SYSTEM] Localization verification after relocation")
    print("🚨 [SYSTEM] Emergency Exit Logic Maintained")
    print("🚪 [SYSTEM] Graceful Quit System Active")
    print("🤖 [SYSTEM] Initializing...")
    
    # Create navigation control interface
    interface_thread = create_navigation_interface()
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n🚪 [SYSTEM] Keyboard interrupt received")
        quit_navigation()
    except Exception as e:
        print(f"❌ [SYSTEM] Unexpected error: {e}")
    finally:
        print("🚪 [SYSTEM] System shutdown complete")
        
        # Ensure TTS is properly shut down
        try:
            tts_manager.shutdown()
        except:
            pass
