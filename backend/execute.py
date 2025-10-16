##### Enhanced Automatic Charging Station - Autonomous Robot Navigation #############
import websocket
import json
import time
import random
import math
import threading
from datetime import datetime
import queue
import threading
import app  # Import the module, not the variables

current_stitched_maps = []
current_map_index = 0
navigation_paused = False
navigation_active = False
force_stop = False
ws_connection = None

#ROBOT_IP = "192.168.0.130"
#WS_PORT = 5000
# Updated maps - Charging station and Normal station
#MAPS = {
 #   "charging_station": "93b9ade3-5258-4de7-ad6b-680d9607c184",  # Map1 - Charging Station
  #  "normal_station": "9ada472a-f5ed-4798-b986-e09fecea80a3"  # Map2 - Normal Station
#}
# Specific map data with coordinates from second code
'''
MAP_DATA = {
    "map1": {
        "id": "93b9ade3-5258-4de7-ad6b-680d9607c184",
        "anchor": {"x": -0.00088, "y": -0.00079, "theta": -0.00836},
        "destination": {"x": 6.10993, "y": -3.73750, "theta": -3.15005}
    },
    "map2": {
        "id": "9ada472a-f5ed-4798-b986-e09fecea80a3",
        "anchor": {"x": -0.00713, "y": 0.04672, "theta": -1.65575},
        "destination": {"x": 0.31500, "y": -6.76637, "theta": 1.63797}
    }
}'''

# Enhanced global variables for station control
go_to_charging = False
go_to_normal = False
current_mission = None
mission_interrupted = False
ws_connection = None
#current_station = "charging"  # Start with charging station
user_command_queue = queue.Queue()
navigation_active = False
force_stop = False
navigation_paused = False

# Navigation status codes
NAVI_CODES = {
    6100: "NAVI_RUNNING - Navigation in operation",
    2007: "NAVI_RUNNING - In navigation",
    6101: "NAVI_NO_PATH - No path found (obstacle detected)",
    2006: "NAVI_COMPLETED - Navigation completed successfully"
}


def send(ws, msg):
    """Send JSON message to robot via WebSocket"""
    ws.send(json.dumps(msg))


def receive_response(ws, timeout=5):
    """Receive and parse JSON response from robot"""
    ws.settimeout(timeout)
    try:
        response = ws.recv()
        return json.loads(response)
    except websocket.WebSocketTimeoutException:
        return None
    except Exception as e:
        print(f"🔍 WebSocket receive error: {e}")
        return None


def receive(ws, timeout=10):
    """Alternative receive function from second code"""
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except Exception:
        return None


def set_map(ws, map_id, timeout=20):
    """Enhanced map setting function combining both approaches"""
    print(f"🗺 Setting map to {map_id}")
    time.sleep(2)  # Allow robot to be ready
    send(ws, {"cmd": "request_set_map", "data": {"mapId": map_id}})
    print(f"🔄 Waiting for map {map_id} to be set...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        res = receive_response(ws, timeout=2)
        if res:
            cmd = res.get("cmd")
            code = res.get("code")
            print(f"📩 Received: {res}")
            if cmd == "response_set_map" and code == 1000:
                print(f"✅ Map {map_id} set successfully")
                return True
    print(f"❌ Timeout: Map {map_id} was not set within {timeout} seconds.")
    return False


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
    send(ws, {"cmd": "request_reset_map"})
    time.sleep(2)


def wait_for_localization(ws, timeout=15):
    """Wait for robot to localize from second code"""
    print("🔍 Waiting for robot to localize...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        res = receive(ws, timeout=2)
        if res and res.get("cmd") == "notify_heart_beat":
            if res.get("code") == 2005:
                print("✅ Robot localized and ready.")
                return True
    print("❌ Localization timeout.")
    return False


def relocate(ws, x, y, theta, mode=2):
    """Force robot to specific position and orientation"""
    print(f"📍 Relocating to position: x={x:.2f}, y={y:.2f}, theta={theta:.2f}")
    send(ws, {"cmd": "request_force_relocate", "data": {"x": x, "y": y, "theta": theta, "mode": mode}})

    start_time = time.time()
    timeout = 15

    while time.time() - start_time < timeout:
        res = receive_response(ws, timeout=1)
        if res:
            cmd = res.get("cmd")
            code = res.get("code")
            if cmd in ["response_relocate_position", "response_force_relocate"]:
                print(f"✅ Relocate response: code={code}")
                return True

    print("⏰ Relocate timeout - continuing anyway")
    return True


def force_relocate(ws, x, y, theta, mode=0):
    """Alternative force relocate function from second code"""
    send(ws, {
        "cmd": "request_force_relocate",
        "data": {"x": x, "y": y, "theta": theta, "mode": mode}
    })
    while True:
        res = receive(ws)
        if res and res.get("cmd") == "response_relocate_position" and res.get("code") == 0:
            print("✅ Relocation successful.")
            return True
        elif res:
            print(f"📩 Received (relocate): {res}")


def stop_current_navigation(ws):
    """Stop current navigation"""
    global force_stop, navigation_active
    print("🛑 Stopping current navigation...")
    force_stop = True
    send(ws, {"cmd": "request_stop_navigation"})
    time.sleep(2)
    navigation_active = False


def enhanced_user_input_listener():
    """Enhanced user input listener with pause/resume functionality"""
    global go_to_charging, go_to_normal, mission_interrupted, force_stop, navigation_paused

    print("\n🎮 ENHANCED CONTROL SYSTEM ACTIVE!")
    print("💡 Press 'c' + ENTER to go to CHARGING STATION")
    print("💡 Press 'e' + ENTER to go to NORMAL STATION")
    print("💡 Press 's' + ENTER to STOP current navigation")
    print("💡 Press 'a' + ENTER to RESUME navigation")
    print("💡 Press 'q' + ENTER to quit the program")
    print("-" * 50)

    while True:
        try:
            user_input = input().strip().lower()

            if user_input == 'c':
                print(f"\n🔋 CHARGING STATION REQUEST at {datetime.now().strftime('%H:%M:%S')}")
                go_to_charging = True
                go_to_normal = False
                mission_interrupted = True
                navigation_paused = False
                user_command_queue.put('charging')

            elif user_input == 'e':
                print(f"\n🎯 NORMAL STATION REQUEST at {datetime.now().strftime('%H:%M:%S')}")
                go_to_normal = True
                go_to_charging = False
                mission_interrupted = True
                navigation_paused = False
                user_command_queue.put('normal')

            elif user_input == 's':
                print(f"\n🛑 STOP NAVIGATION REQUEST at {datetime.now().strftime('%H:%M:%S')}")
                navigation_paused = True
                force_stop = True
                user_command_queue.put('stop')

            elif user_input == 'a':
                print(f"\n▶ RESUME NAVIGATION REQUEST at {datetime.now().strftime('%H:%M:%S')}")
                if navigation_paused:
                    navigation_paused = False
                    force_stop = False
                    user_command_queue.put('resume')
                else:
                    print("ℹ Navigation is not paused")

            elif user_input == 'q':
                print("🛑 Quit requested - stopping program...")
                force_stop = True
                user_command_queue.put('quit')
                break

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"⚠ Input error: {e}")
            continue

def check_user_interrupt():
    global current_stitched_maps, current_map_index, navigation_paused, navigation_active, force_stop

    while not user_command_queue.empty():
        try:
            command_tuple = user_command_queue.get_nowait()
            if isinstance(command_tuple, tuple):
                command, stitched_map_ids = command_tuple
            else:
                command = command_tuple
                stitched_map_ids = []
            if command == 'execute':
                print(f"🚀 Executing stitched maps: {stitched_map_ids}")
                current_stitched_maps = stitched_map_ids
                current_map_index = 0
                navigation_paused = False
                navigation_active = True
                force_stop = False
                return "EXECUTE"
            elif command == 'stop':
                print("🛑 Processing STOP command...")
                #stop_current_navigation(ws)
                navigation_paused = True
                force_stop = True
                return "STOP"
            elif command == 'resume':
                print("▶ Processing RESUME command...")
                if navigation_paused:
                    navigation_paused = False
                    force_stop = False
                    navigation_active = True
                return "RESUME"
            elif command == 'quit':
                print("🚪 Processing QUIT command...")
                force_stop = True
                navigation_active = False
                return "QUIT"
        except queue.Empty:
            break

    return None


def generate_alternative_positions(x, y, theta, attempt):
    """Generate alternative positions for obstacle avoidance"""
    alternatives = []

    if attempt <= 5:
        # Small adjustments
        offset = 0.1 + (attempt - 1) * 0.05
        alternatives = [
            (x + offset, y, theta),
            (x - offset, y, theta),
            (x, y + offset, theta),
            (x, y - offset, theta),
        ]
    else:
        # Larger area exploration
        offset = 0.3 + (attempt - 5) * 0.1
        angle_variations = [0, 30, 45, -30, -45]

        for angle_deg in angle_variations:
            angle_rad = math.radians(angle_deg)
            alternatives.extend([
                (x + offset, y, theta + angle_rad),
                (x - offset, y, theta + angle_rad),
                (x, y + offset, theta + angle_rad),
                (x, y - offset, theta + angle_rad),
            ])

    return alternatives


def get_robot_position(ws):
    """Get current robot position and orientation"""
    send(ws, {"cmd": "request_robot_position"})
    start_time = time.time()
    while time.time() - start_time < 3:
        res = receive_response(ws, timeout=1)
        if res and res.get("cmd") == "response_robot_position":
            data = res.get("data", {})
            return data.get("x"), data.get("y"), data.get("theta")
    return None, None, None


def calculate_distance(x1, y1, x2, y2):
    """Calculate distance between two points"""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def normalize_angle(angle):
    """Normalize angle to [-pi, pi] range"""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def smart_relocation(ws, target_x, target_y, target_theta, attempt):
    """Smart relocation with position correction and directional adjustment"""
    print(f"\n🧭 SMART RELOCATION - Attempt {attempt}")

    # Get current robot position
    curr_x, curr_y, curr_theta = get_robot_position(ws)

    if curr_x is not None and curr_y is not None:
        distance_to_target = calculate_distance(curr_x, curr_y, target_x, target_y)
        angle_diff = normalize_angle(target_theta - curr_theta) if curr_theta is not None else 0

        print(
            f"📍 Current position: x={curr_x:.2f}, y={curr_y:.2f}, θ={curr_theta:.2f}" if curr_theta else f"📍 Current position: x={curr_x:.2f}, y={curr_y:.2f}")
        print(f"🎯 Target position: x={target_x:.2f}, y={target_y:.2f}, θ={target_theta:.2f}")
        print(f"📏 Distance to target: {distance_to_target:.2f}m")
        print(f"🔄 Angle difference: {math.degrees(angle_diff):.1f}°")

        # Strategy based on attempt number and current situation
        if attempt <= 3:
            # First attempts: try direct relocation
            print("🎯 Strategy: Direct relocation to target")
            relocate(ws, target_x, target_y, target_theta)

        elif attempt <= 6:
            # Mid attempts: relocate with position adjustment
            print("🔧 Strategy: Adjusted position relocation")
            # Add small random offset to avoid same problematic position
            offset_x = target_x + random.uniform(-0.2, 0.2)
            offset_y = target_y + random.uniform(-0.2, 0.2)
            relocate(ws, offset_x, offset_y, target_theta)

        elif attempt <= 10:
            # Later attempts: repositioning strategy
            print("🌀 Strategy: Repositioning with rotation")
            if distance_to_target > 0.5:
                # If far from target, relocate closer
                intermediate_x = curr_x + (target_x - curr_x) * 0.7
                intermediate_y = curr_y + (target_y - curr_y) * 0.7
                # Add rotation to find better path
                adjusted_theta = target_theta + math.radians(random.choice([-45, -30, 30, 45]))
                relocate(ws, intermediate_x, intermediate_y, adjusted_theta)
            else:
                # If close to target, just adjust orientation
                adjusted_theta = target_theta + math.radians(random.choice([-90, -45, 45, 90]))
                relocate(ws, curr_x, curr_y, adjusted_theta)

        else:
            # Advanced attempts: circular repositioning
            print("🎪 Strategy: Circular repositioning")
            # Position robot in a circle around target to find clear path
            circle_radius = 0.8 + (attempt - 10) * 0.2
            circle_angle = (attempt * 60) % 360  # Vary position around circle
            circle_x = target_x + circle_radius * math.cos(math.radians(circle_angle))
            circle_y = target_y + circle_radius * math.sin(math.radians(circle_angle))
            # Point towards target
            angle_to_target = math.atan2(target_y - circle_y, target_x - circle_x)
            relocate(ws, circle_x, circle_y, angle_to_target)

    else:
        print("⚠ Could not get current position - using default relocation")
        relocate(ws, target_x, target_y, target_theta)

    # Wait for relocation to settle
    time.sleep(3)


def start_navigation(ws, x, y, theta, speed=0.5):
    """Navigation function from second code"""
    send(ws, {"cmd": "request_start_navigation", "data": {
        "x": x, "y": y, "theta": theta, "speed": speed
    }})
    timeout = 60
    start_time = time.time()

    while True:
        res = receive(ws, timeout=2)
        if not res:
            continue

        cmd = res.get("cmd")
        code = res.get("code")
        msg = res.get("msg")

        print(f"📩 {cmd}: {msg}")
        if cmd == "response_start_navigation" and code == 1001:
            print("🟢 Navigation started.")
        elif cmd == "notify_heart_beat" and code == 2006:
            print("⌛ Navigating...")
        elif cmd == "notify_heart_beat" and code == 2007:
            print("🏁 Reached destination.")
            return True
        elif cmd == "response_start_navigation" and code != 1001:
            print(f"❌ Navigation failed: {msg}")
            return False

        if time.time() - start_time > timeout:
            print("⏰ Navigation timed out.")
            return False


def smart_navigation(ws, dest_x, dest_y, dest_theta, mission_type="normal", max_attempts=20):
    """Smart navigation with obstacle avoidance and user control"""
    global navigation_active, force_stop, navigation_paused

    print(f"🚀 Starting navigation to x={dest_x:.2f}, y={dest_y:.2f}, θ={dest_theta:.2f}")
    print(f"🎯 Mission type: {mission_type.upper()}")

    navigation_active = True
    force_stop = False
    attempt = 0
    last_successful_position = None

    while navigation_active and attempt < max_attempts:
        # Check for user interrupts
        interrupt_result = check_user_interrupt()
        if interrupt_result:
            if interrupt_result == "GO_TO_CHARGING" and mission_type != "charging":
                stop_current_navigation(ws)
                return "GO_TO_CHARGING"
            elif interrupt_result == "GO_TO_NORMAL" and mission_type != "normal":
                stop_current_navigation(ws)
                return "GO_TO_NORMAL"
            elif interrupt_result == "STOP":
                stop_current_navigation(ws)
                print("🛑 Navigation paused - press 'a' to resume")
                while navigation_paused:
                    time.sleep(1)
                    resume_check = check_user_interrupt()
                    if resume_check == "RESUME":
                        print("▶ Resuming navigation...")
                        navigation_active = True
                        force_stop = False
                        break
                    elif resume_check in ["GO_TO_CHARGING", "GO_TO_NORMAL", "QUIT"]:
                        return resume_check
                continue
            elif interrupt_result == "QUIT":
                stop_current_navigation(ws)
                return "QUIT"

        if force_stop:
            return "FORCE_STOPPED"

        attempt += 1
        print(f"\n🎯 Navigation attempt #{attempt}")

        # Check robot position and relocate if needed
        curr_x, curr_y, curr_theta = get_robot_position(ws)
        if curr_x is not None and curr_y is not None:
            distance_to_dest = calculate_distance(curr_x, curr_y, dest_x, dest_y)
            print(f"📍 Current robot position: x={curr_x:.2f}, y={curr_y:.2f}")
            print(f"📏 Distance to destination: {distance_to_dest:.2f}m")

            # Check if robot is facing wrong direction or needs repositioning
            if curr_theta is not None:
                angle_to_dest = math.atan2(dest_y - curr_y, dest_x - curr_x)
                angle_diff = abs(normalize_angle(angle_to_dest - curr_theta))
                print(f"🧭 Angle difference: {math.degrees(angle_diff):.1f}°")

                # If robot is facing completely wrong direction (>120°), relocate
                if angle_diff > math.radians(120) and distance_to_dest > 0.3:
                    print("🔄 Robot facing wrong direction - repositioning...")
                    smart_relocation(ws, dest_x, dest_y, dest_theta, attempt)

        # Generate target position
        target_x, target_y, target_theta = dest_x, dest_y, dest_theta

        if attempt > 3:
            alternatives = generate_alternative_positions(dest_x, dest_y, dest_theta, attempt)
            if alternatives:
                alt_index = (attempt - 4) % len(alternatives)
                target_x, target_y, target_theta = alternatives[alt_index]
                print(f"🎯 Using alternative position: x={target_x:.2f}, y={target_y:.2f}")

        # Smart relocation before navigation attempt
        if attempt > 1:
            smart_relocation(ws, target_x, target_y, target_theta, attempt)

        # Send navigation command
        send(ws, {"cmd": "request_start_navigation", "data": {
            "x": target_x, "y": target_y, "theta": target_theta, "speed": 0.5
        }})

        # Monitor navigation
        start_time = time.time()
        navigation_started = False
        obstacle_count = 0
        stuck_count = 0
        last_position = None
        position_check_time = time.time()

        while navigation_active and not force_stop and not navigation_paused:
            # Check for interrupts during navigation
            interrupt_result = check_user_interrupt()
            if interrupt_result:
                if interrupt_result == "GO_TO_CHARGING" and mission_type != "charging":
                    stop_current_navigation(ws)
                    return "GO_TO_CHARGING"
                elif interrupt_result == "GO_TO_NORMAL" and mission_type != "normal":
                    stop_current_navigation(ws)
                    return "GO_TO_NORMAL"
                elif interrupt_result == "STOP":
                    stop_current_navigation(ws)
                    print("🛑 Navigation paused - press 'a' to resume")
                    while navigation_paused:
                        time.sleep(1)
                        resume_check = check_user_interrupt()
                        if resume_check == "RESUME":
                            print("▶ Resuming navigation...")
                            break
                        elif resume_check in ["GO_TO_CHARGING", "GO_TO_NORMAL", "QUIT"]:
                            return resume_check
                    break
                elif interrupt_result == "QUIT":
                    stop_current_navigation(ws)
                    return "QUIT"

            # Check if robot is stuck (not moving for too long)
            current_time = time.time()
            if current_time - position_check_time > 10:  # Check every 10 seconds
                curr_x, curr_y, curr_theta = get_robot_position(ws)
                if curr_x is not None and curr_y is not None:
                    if last_position is not None:
                        distance_moved = calculate_distance(last_position[0], last_position[1], curr_x, curr_y)
                        if distance_moved < 0.1:  # Moved less than 10cm in 10 seconds
                            stuck_count += 1
                            print(
                                f"⚠ Robot seems stuck (moved only {distance_moved:.2f}m in 10s) - Count: {stuck_count}")

                            if stuck_count >= 3:  # Stuck for 30 seconds
                                print("🚨 Robot is stuck! Performing emergency repositioning...")
                                stop_current_navigation(ws)

                                # Emergency repositioning - move robot to a nearby clear position
                                emergency_positions = [
                                    (curr_x + 0.5, curr_y, curr_theta + math.radians(90)),
                                    (curr_x - 0.5, curr_y, curr_theta + math.radians(90)),
                                    (curr_x, curr_y + 0.5, curr_theta + math.radians(180)),
                                    (curr_x, curr_y - 0.5, curr_theta + math.radians(180)),
                                ]

                                emergency_pos = emergency_positions[stuck_count % len(emergency_positions)]
                                print(f"🚑 Emergency relocation to: x={emergency_pos[0]:.2f}, y={emergency_pos[1]:.2f}")
                                relocate(ws, emergency_pos[0], emergency_pos[1], emergency_pos[2])
                                break
                        else:
                            stuck_count = 0  # Reset stuck counter if robot is moving

                    last_position = (curr_x, curr_y, curr_theta)
                    position_check_time = current_time

            res = receive_response(ws, timeout=1)

            if res:
                cmd = res.get("cmd")
                code = res.get("code")
                msg = res.get("msg", "")

                if cmd == "response_start_navigation":
                    if code == 1001 or 'success' in msg.lower():
                        print("✅ Navigation command accepted")
                        navigation_started = True
                    elif code == 1005:
                        print("⚠ Robot not localized - performing smart relocation...")
                        reset_map(ws)
                        time.sleep(3)
                        smart_relocation(ws, target_x, target_y, target_theta, attempt)
                        break
                    else:
                        print(f"⚠ Navigation start issue: code={code}, msg={msg}")
                        if code == 6101:
                            print("🚧 No path found - trying repositioning...")
                            smart_relocation(ws, target_x, target_y, target_theta, attempt)
                        break

                elif cmd == "notify_heart_beat":
                    if code == 6100 or code == 2007:
                        print("⚡ Navigation in progress...")
                        navigation_started = True
                        stuck_count = 0  # Reset stuck counter when actively navigating
                    elif code == 6101:
                        obstacle_count += 1
                        print(f"🚧 Obstacle detected #{obstacle_count}")

                        # If too many obstacles, try repositioning
                        if obstacle_count > 5:
                            print("🔄 Too many obstacles - repositioning robot...")
                            stop_current_navigation(ws)
                            smart_relocation(ws, target_x, target_y, target_theta, attempt)
                            break

                        time.sleep(2)
                    elif code == 2006:
                        if navigation_started:
                            print("🏆 DESTINATION REACHED!")
                            navigation_active = False
                            return "SUCCESS"

            # Timeout check
            if time.time() - start_time > 120:  # 2 minutes per attempt
                print("⏰ Attempt timeout - trying repositioning approach")
                stop_current_navigation(ws)
                smart_relocation(ws, target_x, target_y, target_theta, attempt)
                break

        # Brief pause before next attempt
        time.sleep(1)

    print(f"❌ Navigation failed after {max_attempts} attempts")
    return "FAILED"


def go_to_charging_station(ws):
    """Navigate to charging station using both approaches"""
    global current_station

    print("\n🔋 GOING TO CHARGING STATION")

    # Use the enhanced map setting
    if not set_map(ws, MAPS["charging_station"]):
        print("❌ Failed to switch to charging station map!")
        return False

    current_station = "charging"

    # Try to get points dynamically first
    points = get_points(ws, MAPS["charging_station"])

    if points:
        # Use dynamic points if available
        anchor = next((p for p in points if p.get("type") == "anchor_point"), None)
        destination = next((p for p in points if p.get("type") == "destination"), None)

        if not anchor:
            print("❌ Missing anchor point!")
            return False

        print(f"📌 Anchor: x={anchor['x']:.2f}, y={anchor['y']:.2f}")
        reset_map(ws)
        relocate(ws, anchor["x"], anchor["y"], anchor["theta"])

        if destination:
            print(f"🔋 Destination: x={destination['x']:.2f}, y={destination['y']:.2f}")
            result = smart_navigation(ws, destination["x"], destination["y"], destination["theta"], "charging")
        else:
            print("🔋 ARRIVED AT CHARGING STATION ANCHOR!")
            return "SUCCESS"
    else:
        # Fallback to hardcoded MAP_DATA
        print("📍 Using hardcoded map data for charging station...")
        map_info = MAP_DATA["map1"]

        print("📍 Relocating to map1 anchor...")
        force_relocate(ws, **map_info["anchor"])
        wait_for_localization(ws)

        print("📍 Relocating again to map1 destination (to stabilize)...")
        force_relocate(ws, **map_info["destination"])
        wait_for_localization(ws)

        print("🚗 Navigating to map1 destination...")
        if start_navigation(ws, **map_info["destination"]):
            result = "SUCCESS"
        else:
            print("❌ Map1 navigation failed.")
            result = "FAILED"

    if result == "SUCCESS":
        print("🔋 ARRIVED AT CHARGING STATION!")
        return "SUCCESS"
    else:
        return result

def navigate_stitched_maps(ws):
    global current_stitched_maps, current_map_index, navigation_paused, navigation_active, force_stop

    while current_map_index < len(current_stitched_maps):
        # Check for stop command
        if force_stop:
            print("🛑 Navigation stopped by user (force_stop set).")
            break

        map_id = current_stitched_maps[current_map_index]
        map_name = f"map{current_map_index+1}"
        print(f"🗺 Navigating map {current_map_index+1}/{len(current_stitched_maps)}: {map_id}")

        # Set the map and get waypoints
        set_map(ws, map_id)
        points = get_points(ws, map_id)
        if not points:
            print(f"❌ No points found for {map_name}")
            break

        anchor = next((p for p in points if p.get("type") == "anchor_point"), None)
        dest = next((p for p in points if p.get("type") == "destination"), None)
        if not anchor or not dest:
            print(f"❌ {map_name}: Missing anchor or destination point!")
            break

        # Relocate to anchor
        if not relocate(ws, anchor["x"], anchor["y"], anchor["theta"]):
            break

        # Navigation loop with pause/resume support
        while navigation_paused:
            print("⏸ Navigation paused. Waiting to resume...")
            time.sleep(1)
            check_user_interrupt()  # This will update navigation_paused/force_stop

        # Start navigation to destination - FIXED: Use existing start_navigation function
        result = start_navigation(ws, dest["x"], dest["y"], dest["theta"])

        if force_stop:
            print("🛑 Navigation stopped by user (force_stop set).")
            break

        if result:
            print(f"✅ Finished map {map_id}")
            current_map_index += 1
        else:
            print(f"❌ Navigation failed for map {map_id}")
            break

    print("🏁 All stitched maps navigation complete.")
    navigation_active = False

def relocate_with_retry(ws, x, y, theta, max_retries=3):
    """Relocate robot with retry mechanism"""
    for attempt in range(max_retries):
        print(f"🔄 Relocation attempt {attempt + 1}/{max_retries}")
        
        if relocate(ws, x, y, theta):
            print("✅ Relocation successful")
            return True
        
        if attempt < max_retries - 1:
            print(f"⚠ Relocation failed, retrying in 2 seconds...")
            time.sleep(2)
    
    print("❌ Relocation failed after all attempts")
    return False

def go_to_normal_station(ws):
    """Navigate to normal station using both approaches"""
    global current_station

    print("\n🎯 GOING TO NORMAL STATION")

    # Use the enhanced map setting
    if not set_map(ws, MAPS["normal_station"]):
        print("❌ Failed to switch to normal station map!")
        return False

    current_station = "normal"

    # Try to get points dynamically first
    points = get_points(ws, MAPS["normal_station"])

    if points:
        # Use dynamic points if available
        anchor = next((p for p in points if p.get("type") == "anchor_point"), None)
        destination = next((p for p in points if p.get("type") == "destination"), None)

    if not anchor:
            print("❌ Missing anchor point!")
            return False

    print(f"📌 Anchor: x={anchor['x']:.2f}, y={anchor['y']:.2f}")

    reset_map(ws)
    relocate(ws, anchor["x"], anchor["y"], anchor["theta"])

    if destination:
        print(f"🎯 Destination: x={destination['x']:.2f}, y={destination['y']:.2f}")
        result = smart_navigation(ws, destination["x"], destination["y"], destination["theta"], "normal")

        if result == "SUCCESS":
            print("🎯 ARRIVED AT NORMAL STATION!")
            return "SUCCESS"
        else:
            return result
    else:
        print("🎯 ARRIVED AT NORMAL STATION ANCHOR!")
        return "SUCCESS"


def execute_station_sequence(ws):
    """Execute station sequence with user control"""
    global go_to_charging, go_to_normal, force_stop

    print("\n🤖 STATION SEQUENCE SYSTEM ACTIVE")
    cycle_count = 0

    while True:
        cycle_count += 1
        print(f"\n🔄 === CYCLE #{cycle_count} ===")

        # Check for user commands
        interrupt_result = check_user_interrupt()
        if interrupt_result == "QUIT":
            break
        elif interrupt_result == "STOP":
            print("🛑 Sequence paused...")
            continue

        # Phase 1: Charging Station
        if not go_to_normal:
            print("\n🔋 === CHARGING STATION PHASE ===")
            result = go_to_charging_station(ws)

            if result == "GO_TO_NORMAL":
                go_to_normal = True
                go_to_charging = False
                continue
            elif result == "QUIT":
                break
            elif result == "SUCCESS":
                print("✅ Charging phase completed!")
                time.sleep(2)

        # Check for commands between phases
        interrupt_result = check_user_interrupt()
        if interrupt_result == "QUIT":
            break
        elif interrupt_result == "GO_TO_CHARGING":
            go_to_charging = True
            go_to_normal = False
            continue

        # Phase 2: Normal Station
        if not go_to_charging:
            print("\n🎯 === NORMAL STATION PHASE ===")
            result = go_to_normal_station(ws)

            if result == "GO_TO_CHARGING":
                go_to_charging = True
                go_to_normal = False
                continue
            elif result == "QUIT":
                break
            elif result == "SUCCESS":
                print("✅ Normal phase completed!")
                time.sleep(2)

        # Reset flags for next cycle
        if not go_to_charging and not go_to_normal:
            print(f"🔄 CYCLE #{cycle_count} COMPLETED!")
            time.sleep(3)

    print("🏁 SEQUENCE ENDED")


def main():
    global ws_connection, navigation_active
    print("🔌🔌🔌executing execute.py")
    while True:
        try:
            # Always get the latest values
            found_ip = app.found_ip
            found_port = app.found_port if app.found_port else 5000
            #app.discover_robot()
            if not found_ip:
                print("❌ Robot IP not found. Retrying in 5 seconds...main execute.py..")
                app.discover_robot()
                time.sleep(2)
                continue
            ws = websocket.create_connection(f"ws://{found_ip}:{found_port}")
            ws_connection = ws
            print("🔌 Connected to robot!")
            print("🤖 ENHANCED NAVIGATION SYSTEM READY")
            # Wait for user interrupts until quit
            while True:
                print("🔄 Waiting for user commands...")
                interrupt_result = check_user_interrupt()
                if interrupt_result == "QUIT":
                    print("🚪 Quit command received. Closing connection.")
                    break
                time.sleep(1)
            break  # Exit outer loop after quit
        except Exception as e:
            print(f"❌ Error: {e}")
            print("🔄 Retrying connection in 5 seconds..execute.py...")
            time.sleep(5)
            force_stop = True
        finally:
            if ws_connection:
                try:
                    stop_current_navigation(ws_connection)
                    ws_connection.close()
                    print("🔌 Connection closed")
                except:
                    pass

robot_thread = threading.Thread(target=main, daemon=True)
robot_thread.start()