import os
from flask import Flask, render_template, request, Response, redirect, url_for, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
import socket
import threading
import subprocess
import platform
import requests
import json
import time
import websocket
import paramiko
from flask import Flask, request, jsonify
import queue
#from execution import run_multi_map_navigation_no_tts  # Import this function (see below)
from execution import run_multi_map_navigation_with_charging

from execution import emergency_exit_event, trigger_emergency_exit

load_dotenv()

app = Flask(__name__)
CORS(app)

@app.after_request
def add_no_cache_headers(response):
    """Prevent client/proxy caching so refreshed status reflects current network."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/api/robot/emergency_exit", methods=["POST"])
def api_robot_emergency_exit():
    global emergency_exit_map_id
    # Use your fixed emergency map id
    emergency_exit_map_id = "a02abac3-e4f2-4fb0-8c29-d2086fcd98a9"
    trigger_emergency_exit()
    return jsonify({"success": True, "message": "Emergency exit triggered!"})


env_username = os.getenv("FLASK_USERNAME")
env_password = os.getenv("FLASK_PASSWORD")

# Global variables for WiFi checking
ROBOT_PORT = 5000
#SUBNET_PREFIX = "192.168.0."
found_ip = None
device_wifi_name = None
device_ip = None

navigation_paused = False

# Discovery guard and robot websocket signature
discovery_lock = threading.Lock()
KNOWN_ROBOT_CMDS = {
    "notify_heart_beat",
    "notify_battery_info",
    "notify_emr_status",
    "notify_robot_status",
    "response_set_map",
    "response_map_list",
    "notify_map_list",
    "response_get_map_list"
}

# Navigation manager globals
navigation_queue = queue.Queue()
navigation_thread = None
navigation_status = {
    'active': False,
    'paused': False,
    'stopped': False,
    'current_map': None,
    'step': None,
    'error': None,
    'completed': False
}
# Thread-safe navigation control
navigation_control = {
    #'force_stop': threading.Event(),
    #'quit': threading.Event(),
    'paused': threading.Event()
}

def get_device_wifi_info():
    """Get current device's WiFi name and IP address"""
    global device_wifi_name, device_ip
    # Reset cached values to avoid showing stale network names
    device_wifi_name = None
    device_ip = None
    
    try:
        # Get local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        device_ip = s.getsockname()[0]
        s.close()
        print(f"🔍 Device IP detected: {device_ip}")
        
        # Get WiFi name based on operating system
        system = platform.system()
        print(f"🔍 Operating System: {system}")
        
        if system == "Windows":
            # Method 1: Try netsh wlan show interfaces (more reliable)
            try:
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], 
                                      capture_output=True, text=True, encoding='utf-8')
                print(f"🔍 Netsh command output:")
                print(result.stdout)
                
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        line = line.strip()
                        # Look for SSID line (not BSSID)
                        if line.startswith('SSID') and 'BSSID' not in line and ':' in line:
    # Only pick the SSID line, not Signal or other lines
                            device_wifi_name = line.split(':', 1)[1].strip()
                            print(f"✅ WiFi name found: {device_wifi_name}")
                            break
                        # Alternative pattern
                        elif 'Profile' in line and ':' in line:
                            potential_name = line.split(':', 1)[1].strip()
                            if potential_name and potential_name != "":
                                device_wifi_name = potential_name
                                print(f"✅ WiFi profile found: {device_wifi_name}")
                                print(f"SSID parsed: '{device_wifi_name}'")
                                break
            except Exception as e:
                print(f"⚠️ Method 1 failed: {e}")
            
            # Method 2: If method 1 failed, try PowerShell
            if not device_wifi_name:
                try:
                    ps_command = 'Get-NetConnectionProfile | Where-Object {$_.NetworkCategory -ne "DomainAuthenticated"} | Select-Object -First 1 -ExpandProperty Name'
                    result = subprocess.run(['powershell', '-Command', ps_command], 
                                          capture_output=True, text=True, encoding='utf-8')
                    if result.returncode == 0 and result.stdout.strip():
                        # Use the full line as SSID; do not split to keep spaces in SSID
                        device_wifi_name = result.stdout.strip()
                        print(f"✅ WiFi name found via PowerShell: {device_wifi_name}")
                except Exception as e:
                    print(f"⚠️ Method 2 failed: {e}")
            
            # Method 3: Try another netsh approach
            if not device_wifi_name:
                try:
                    result = subprocess.run(['netsh', 'wlan', 'show', 'profile'], 
                                          capture_output=True, text=True, encoding='utf-8')
                    if result.returncode == 0:
                        # Get the connected profile by checking interfaces again
                        interface_result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], 
                                                        capture_output=True, text=True, encoding='utf-8')
                        for line in interface_result.stdout.split('\n'):
                            if 'State' in line and 'connected' in line.lower():
                                # Found connected interface, now get its SSID
                                for ssid_line in interface_result.stdout.split('\n'):
                                    if 'SSID' in ssid_line and 'BSSID' not in ssid_line:
                                        parts = ssid_line.split(':', 1)
                                        if len(parts) > 1:
                                            device_wifi_name = parts[1].strip()
                                            print(f"✅ WiFi name found via method 3: {device_wifi_name}")
                                            break
                                break
                except Exception as e:
                    print(f"⚠️ Method 3 failed: {e}")
        
        elif system == "Darwin":  # macOS
            try:
                result = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'], 
                                      capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if ' SSID:' in line:
                        device_wifi_name = line.split(':')[1].strip()
                        break
            except:
                # Alternative for macOS
                try:
                    result = subprocess.run(['networksetup', '-getairportnetwork', 'en0'], 
                                          capture_output=True, text=True)
                    if 'Current Wi-Fi Network:' in result.stdout:
                        device_wifi_name = result.stdout.split('Current Wi-Fi Network:')[1].strip()
                except:
                    pass
        
        elif system == "Linux":
            # Try multiple methods for Linux
            methods = [
                ['iwgetid', '-r'],
                ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                ['iwconfig']
            ]
            
            for method in methods:
                try:
                    result = subprocess.run(method, capture_output=True, text=True)
                    if result.returncode == 0:
                        if method[0] == 'iwgetid':
                            device_wifi_name = result.stdout.strip()
                            break
                        elif method[0] == 'nmcli':
                            for line in result.stdout.split('\n'):
                                if line.startswith('yes:'):
                                    device_wifi_name = line.split(':')[1]
                                    break
                        elif method[0] == 'iwconfig':
                            for line in result.stdout.split('\n'):
                                if 'ESSID:' in line:
                                    device_wifi_name = line.split('ESSID:"')[1].split('"')[0]
                                    break
                    if device_wifi_name:
                        break
                except:
                    continue
                
    except Exception as e:
        print(f"❌ Error getting device info: {e}")
        import traceback
        traceback.print_exc()
found_port = None

def test_robot_connection(robot_ip):
    """Test various connection methods to the robot"""
    print(f"🔍 Testing robot connection methods for {robot_ip}...")
    
    # Test common ports
    common_ports = [5000, 8080, 80, 443, 3000, 8000, 9090, 22, 23]
    open_ports = []
    
    for port in common_ports:
        try:
            sock = socket.create_connection((robot_ip, port), timeout=1)
            sock.close()
            open_ports.append(port)
            print(f"   ✅ Port {port} is open")
        except:
            pass
    
    if open_ports:
        print(f"   Open ports found: {open_ports}")
    else:
        print("   No common ports found open")
    
    return open_ports

def set_navigation_status(**kwargs):
    global navigation_status
    navigation_status.update(kwargs)

def validate_robot_ip(ip, ws_port=5000, handshake_timeout=2.0, listen_timeout=2.0):
    """Validate that the given IP belongs to the robot by performing a WebSocket handshake and
    checking for expected messages. Returns True if validated, False otherwise."""
    try:
        ws = websocket.create_connection(f"ws://{ip}:{ws_port}", timeout=handshake_timeout)
        ws.settimeout(listen_timeout)
        try:
            ws.send(json.dumps({"cmd": "request_heart_beat"}))
        except Exception:
            pass
        start_time = time.time()
        while time.time() - start_time < listen_timeout:
            try:
                res = ws.recv()
                data = json.loads(res)
                cmd = data.get("cmd")
                if cmd and cmd in KNOWN_ROBOT_CMDS:
                    ws.close()
                    return True
                # Some firmware replies with a generic structure but valid data
                if cmd and isinstance(data.get("data", {}), dict):
                    ws.close()
                    return True
            except Exception:
                continue
        ws.close()
        return False
    except Exception:
        return False

def get_robot_wifi_info(robot_ip):
    """Enhanced robot WiFi information retrieval"""
    print(f"🔍 Attempting to get WiFi info from robot at {robot_ip}...")
    
    # First, test what ports are available
    open_ports = test_robot_connection(robot_ip)
    
    # Try HTTP endpoints on discovered ports (restrict to expected WS/http bridge port only)
    http_ports = [port for port in open_ports if port in [5000]]
    if not http_ports:
        http_ports = [5000]  # Default fallback
    
    # Common API endpoints to try
    api_endpoints = [
        "/api/network",
        "/api/wifi",
        "/api/status",
        "/network-info",
        "/wifi-info", 
        "/status",
        "/info",
        "/config",
        "/system/info",
        "/v1/network",
        "/v1/status"
    ]
    
    for port in http_ports:
        print(f"   🔍 Trying port {port}...")
        for endpoint in api_endpoints:
            try:
                url = f"http://{robot_ip}:{port}{endpoint}"
                print(f"      Testing: {url}")
                response = requests.get(url, timeout=2)
                print(f"      Status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"      Response: {json.dumps(data, indent=2)[:200]}...")
                        
                        # Try to extract WiFi info from response
                        ssid = (data.get('wifi_ssid') or 
                               data.get('ssid') or 
                               data.get('network_name') or
                               data.get('network', {}).get('ssid') if isinstance(data.get('network'), dict) else None)
                        
                        ip = (data.get('wifi_ip') or 
                             data.get('ip') or 
                             data.get('local_ip') or
                             data.get('network', {}).get('ip') if isinstance(data.get('network'), dict) else None)
                        
                        if ssid:
                            print(f"      ✅ Found WiFi SSID: {ssid}")
                            return ssid, ip or robot_ip
                            
                    except json.JSONDecodeError:
                        # Ignore non-JSON responses to avoid false positives like Express welcome pages
                        print("      ⚠️ Non-JSON HTTP 200 response ignored")
                        continue
            except requests.exceptions.RequestException as e:
                print(f"      ❌ Request failed: {e}")
                continue
            except Exception as e:
                print(f"      ❌ Unexpected error: {e}")
                continue
    
    # Try simple TCP connection to get basic info
    try:
        print(f"   🔍 Trying simple TCP connection...")
        sock = socket.create_connection((robot_ip, 5000), timeout=2)
        sock.send(b"GET /info HTTP/1.1\r\nHost: " + robot_ip.encode() + b"\r\r")
        response = sock.recv(1024).decode('utf-8', errors='ignore')
        sock.close()
        if response:
            print(f"      Raw response: {response[:200]}...")
    except Exception as e:
        print(f"      TCP connection failed: {e}")
    
    return None, robot_ip

def check_same_network(device_ip, robot_ip):
    """Check if both devices are likely on the same network"""
    device_subnet = '.'.join(device_ip.split('.')[:-1])
    robot_subnet = '.'.join(robot_ip.split('.')[:-1])
    
    if device_subnet == robot_subnet:
        print(f"✅ NETWORK MATCH: Both devices are on subnet {device_subnet}.x")
        return True
    else:
        print(f"⚠️ SUBNET MISMATCH: Device on {device_subnet}.x, Robot on {robot_subnet}.x")
        return False

def check_ip(ip):
    global found_ip
    try:
        s = socket.create_connection((ip, ROBOT_PORT), timeout=0.5)
        s.close()
        # Only mark as found if IP validates as robot via WebSocket
        if validate_robot_ip(ip, ws_port=ROBOT_PORT):
            with discovery_lock:
                if not found_ip:
                    print(f"✅ Robot validated at {ip}")
                    found_ip = ip
        else:
            print(f"⚠️ Skipping {ip}: open port but not a robot")
    except:
        pass

@app.route("/")
def home():
    return "Hello, Flask!"

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    print(data)
    email = data.get("email")
    password = data.get("password")

    if email == env_username and password == env_password:
        print('cvbbcvb')
        return jsonify({"success": True, "message": "Login successful"})
    else:
        return jsonify({"success": False, "message": "Invalid credentials"})

    return render_template('login.html')

@app.route("/api/network/status", methods=["GET"])
def get_network_status():
    """Get current device network status"""
    try:
        get_device_wifi_info()
        
        if device_wifi_name and device_ip:
            return jsonify({
                "success": True,
                "connected": True,
                "network_name": device_wifi_name,
                "device_ip": device_ip,
                "message": "Successfully connected to network"
            })
        else:
            return jsonify({
                "success": True,
                "connected": False,
                "network_name": None,
                "device_ip": device_ip,
                "message": "Not connected to any network"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "connected": False,
            "network_name": None,
            "device_ip": None,
            "message": f"Error getting network status: {str(e)}"
        })

@app.route("/api/robot/discover", methods=["GET"])
def discover_robot():
    """Discover robot on the network"""
    global found_ip
    
    try:
        # Reset found_ip
        found_ip = None
        
        # Get device info first
        # ...existing code...
        get_device_wifi_info()

        # Dynamically determine subnet prefix from device_ip
        if device_ip:
            subnet_prefix = '.'.join(device_ip.split('.')[:3]) + '.'
        else:
            subnet_prefix = "192.168.0."  # fallback

        # Scan for robot
        print("🔍 Scanning for robot on port 5000 with validation...")
        threads = []
        for i in range(1, 255):
            ip = f"{subnet_prefix}{i}"
            t = threading.Thread(target=check_ip, args=(ip,))
            threads.append(t)
            t.start()
        # ...existing code...
        
        for t in threads:
            t.join()
        
        if found_ip:
            # Check if they're on the same subnet
            same_network = False
            if device_ip:
                same_network = check_same_network(device_ip, found_ip)
            
            # Get robot WiFi information
            robot_wifi_name, robot_ip = get_robot_wifi_info(found_ip)
            found_port = 5000  # validated port

            return jsonify({
                "success": True,
                "robot_found": True,
                "robot_ip": found_ip,
                "robot_wifi_name": robot_wifi_name,
                "device_wifi_name": device_wifi_name,
                "device_ip": device_ip,
                "same_network": same_network,
                "connected": device_wifi_name == robot_wifi_name if robot_wifi_name else same_network,
                "robot_port": found_port,
                "message": "Robot discovered successfully"
            })
        else:
            return jsonify({
                "success": True,
                "robot_found": False,
                "robot_ip": None,
                "robot_wifi_name": None,
                "device_wifi_name": device_wifi_name,
                "device_ip": device_ip,
                "same_network": False,
                "connected": False,
                "message": "Robot not found on the network"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "robot_found": False,
            "robot_ip": None,
            "robot_wifi_name": None,
            "device_wifi_name": None,
            "device_ip": None,
            "same_network": False,
            "connected": False,
            "message": f"Error discovering robot: {str(e)}"
        })

@app.route("/api/robot/upcoming_map", methods=["GET"])
def api_robot_upcoming_map():
    try:
        import execution
        # Get upcoming map information from execution module
        upcoming_map_ids = getattr(execution, "upcoming_map_ids", [None, None])
        upcoming_map_names = getattr(execution, "upcoming_map_names", [None, None])
        return jsonify({
            "success": True,
            "upcoming_map_id_1": upcoming_map_ids[0],
            "upcoming_map_name_1": upcoming_map_names[0],
            "upcoming_map_id_2": upcoming_map_ids[1],
            "upcoming_map_name_2": upcoming_map_names[1]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/current_map", methods=["GET"])
def api_robot_current_map():
    try:
        import execution
        # Get current map information from execution module
        current_map_id = getattr(execution, "current_map_id", None)
        current_map_name = getattr(execution, "current_map_name", None)
        upcoming_map_ids = getattr(execution, "upcoming_map_ids", [None, None])
        upcoming_map_names = getattr(execution, "upcoming_map_names", [None, None])
        
        return jsonify({
            "success": True,
            "current_map_id": current_map_id,
            "current_map_name": current_map_name,
            "upcoming_map_id_1": upcoming_map_ids[0],
            "upcoming_map_name_1": upcoming_map_names[0],
            "upcoming_map_id_2": upcoming_map_ids[1],
            "upcoming_map_name_2": upcoming_map_names[1]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/refresh_maps_cache", methods=["POST"])
def api_robot_refresh_maps_cache():
    try:
        import execution
        global found_ip
        
        if not found_ip:
            discover_robot()
            robot_ip = found_ip
        else:
            robot_ip = found_ip
            
        if not robot_ip:
            return jsonify({"success": False, "message": "Robot not found"})
        
        # Get fresh maps from robot
        maps_result = get_robot_maps(robot_ip)
        if maps_result.get("success") and maps_result.get("maps"):
            # Update the cache in execution module
            execution.update_robot_maps_cache(maps_result["maps"])
            return jsonify({
                "success": True, 
                "message": f"Maps cache refreshed with {len(maps_result['maps'])} maps",
                "maps_count": len(maps_result["maps"])
            })
        else:
            return jsonify({"success": False, "message": "Failed to fetch maps from robot"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    

@app.route("/api/robot/quit", methods=["POST"])
def api_robot_quit():
    try:
        import execution
        execution.quit_navigation()
        # Clear map tracking
        execution.clear_map_tracking()
        # Clear stitchedMapIds list (if stored globally)
        global stitched_map_ids
        stitched_map_ids = []
        # Also clear navigation queue if used
        if 'navigation_queue' in globals():
            while not navigation_queue.empty():
                navigation_queue.get()
        # Optionally reset navigation status
        set_navigation_status(active=False, paused=False, stopped=True, error="Navigation quit by user", completed=False, current_map=None, step=None)
        return jsonify({"success": True, "message": "Quit command sent, navigation cancelled, stitchedMapIds cleared"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    

@app.route("/api/robot/undock", methods=["POST"])
def api_robot_undock():
    global found_ip, found_port
    if not found_ip:
        discover_robot()
    if not found_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    if not found_port:
        found_port = 5000
    try:
        ws = websocket.create_connection(f"ws://{found_ip}:{found_port}")
        # Send undock command (as per your API spec)
        ws.send(json.dumps({"cmd": "request_cancel_charge"}))
        start_time = time.time()
        success = False
        while time.time() - start_time < 30:
            res = ws.recv()
            print("✅✅✅Undock response:", res)
            data = json.loads(res)
            if data.get("cmd") == "response_dock_ctrl" and data.get("code") == 0:
                success = True
                break
        ws.close()
        if success:
            return jsonify({"success": True, "message": "Robot undocked from charging pile."})
        else:
            return jsonify({"success": False, "message": "Failed to undock from charging pile."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/stop", methods=["POST"])
def api_robot_stop():
    try:
        navigation_control['paused'].set()
        set_navigation_status(paused=True)
        return jsonify({"success": True, "message": "Navigation stopped"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/auto_charge", methods=["POST"])
def api_robot_auto_charge():
    global found_ip, found_port
    if not found_ip:
        discover_robot()
    if not found_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    if not found_port:
        found_port = 5000
    try:
        ws = websocket.create_connection(f"ws://{found_ip}:{found_port}")
        # Set map (use your CHARGE_POINT map id, or get from request)
        MAP_ID = "be6e76e5-3612-4eb7-89ee-6bc09f222634"
        CHARGE_POINT = {
            "x": -0.000742468717372349,
            "y": -0.017879863624663088,
            "theta": -0.016518184324892632
        }
        # Set map
        ws.send(json.dumps({"cmd": "request_set_map", "data": {"mapId": MAP_ID}}))
        while True:
            res = ws.recv()
            data = json.loads(res)
            if data.get("cmd") == "response_set_map" and data.get("code") == 1000:
                break
        # Get current location
        ws.send(json.dumps({"cmd": "request_heart_beat"}))
        location = None
        start_time = time.time()
        while time.time() - start_time < 10:
            res = ws.recv()
            data = json.loads(res)
            if data.get("cmd") == "notify_heart_beat" and "x" in data.get("data", {}):
                location = data["data"]
                break
        if not location:
            ws.close()
            return jsonify({"success": False, "message": "Could not get current location."})
        # Force relocate
        ws.send(json.dumps({
            "cmd": "request_force_relocate",
            "data": {"x": location["x"], "y": location["y"], "theta": location["theta"], "mode": 0}
        }))
        while True:
            res = ws.recv()
            data = json.loads(res)
            if data.get("cmd") == "response_relocate_position" and data.get("code") == 0:
                break
        # Dock charge
        ws.send(json.dumps({
            "cmd": "request_dock_charge",
            "data": {"mapId": MAP_ID, "x": CHARGE_POINT["x"], "y": CHARGE_POINT["y"], "theta": CHARGE_POINT["theta"]}
        }))
        docked = False
        start_time = time.time()
        while time.time() - start_time < 90:
            res = ws.recv()
            data = json.loads(res)
            if data.get("cmd") == "response_dock_ctrl":
                if data.get("code") == 0:
                    docked = True
                    break
                elif data.get("code") == 6016:
                    break
        ws.close()
        if docked:
            return jsonify({"success": True, "message": "Robot is charging."})
        else:
            return jsonify({"success": False, "message": "Failed to dock and charge."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/resume", methods=["POST"])
def api_robot_resume():
    try:
        navigation_control['paused'].clear()
        set_navigation_status(paused=False)
        return jsonify({"success": True, "message": "Navigation resumed"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/status", methods=["GET"])
def get_robot_status():
    """Get comprehensive robot and network status"""
    try:
        # Get device info
        get_device_wifi_info()
        
        # Discover robot
        discovery_result = discover_robot()
        discovery_data = discovery_result.get_json()
        
        if discovery_data["success"] and discovery_data["robot_found"]:
            return jsonify({
                "success": True,
                "device": {
                    "wifi_name": device_wifi_name,
                    "ip": device_ip,
                    "connected": True if device_wifi_name else False
                },
                "robot": {
                    "ip": discovery_data["robot_ip"],
                    "wifi_name": discovery_data["robot_wifi_name"],
                    "found": True
                },
                "network": {
                    "same_network": discovery_data["same_network"],
                    "connected": discovery_data["connected"]
                },
                "message": "Robot and network status retrieved successfully"
            })
        else:
            return jsonify({
                "success": True,
                "device": {
                    "wifi_name": device_wifi_name,
                    "ip": device_ip,
                    "connected": True if device_wifi_name else False
                },
                "robot": {
                    "ip": None,
                    "wifi_name": None,
                    "found": False
                },
                "network": {
                    "same_network": False,
                    "connected": False
                },
                "message": "Device connected but robot not found"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "device": {
                "wifi_name": None,
                "ip": None,
                "connected": False
            },
            "robot": {
                "ip": None,
                "wifi_name": None,
                "found": False
            },
            "network": {
                "same_network": False,
                "connected": False
            },
            "message": f"Error getting status: {str(e)}"
        })

def get_robot_battery_status(robot_ip, ws_port=5000, listen_duration=10):
    """Connect to robot via WebSocket and get battery status"""
    try:
        ws = websocket.create_connection(f"ws://{robot_ip}:{ws_port}")
        ws.settimeout(listen_duration)
        start_time = time.time()
        while time.time() - start_time < listen_duration:
            try:
                res = ws.recv()
                data = json.loads(res)
                if data.get("cmd") == "notify_battery_info":
                    battery = data["data"].get("battery")
                    status = data["data"].get("status")
                    charging = status
                    ws.close()
                    return {"success": True, "battery": battery, "charging": charging}
            except Exception as e:
                continue
        ws.close()
        return {"success": False, "message": "No battery info received in time."}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.route("/api/robot/battery", methods=["GET"])
def api_robot_battery():
    global found_ip
    # Use the last discovered robot IP
    robot_ip = found_ip
    if not robot_ip:
        # Try to discover robot if not already found
        discover_robot()
        robot_ip = found_ip
    if not robot_ip:
        return jsonify({"success": False, "message": "Robot not found on the network."}), 404
    result = get_robot_battery_status(robot_ip)
    return jsonify(result)

def get_robot_maps(robot_ip, ws_port=5000, timeout=10):
    import time
    try:
        ws = websocket.create_connection(f"ws://{robot_ip}:{ws_port}")
        ws.settimeout(timeout)
        # Try all known map list commands
        test_commands = [
            {"cmd": "request_list_maps"},
            {"cmd": "request_map_list"},
            {"cmd": "get_map_list"},
            {"cmd": "request_get_map_list"},
        ]
        for cmd in test_commands:
            ws.send(json.dumps(cmd))
            time.sleep(1)
        start_time = time.time()
        found_maps = []
        while time.time() - start_time < timeout:
            try:
                response = ws.recv()
                data = json.loads(response)
                # Look for a map list inside the message
                if "maps" in data.get("data", {}):
                    maps = data["data"]["maps"]
                    for m in maps:
                        found_maps.append({
                            "name": m.get("name"),
                            "id": m.get("id")
                        })
                    break
                elif "mapList" in data.get("data", {}):
                    maps = data["data"]["mapList"]
                    for m in maps:
                        found_maps.append({
                            "name": m.get("name"),
                            "id": m.get("mapId")
                        })
                    break
            except Exception as e:
                break
        ws.close()
        if found_maps:
            return {"success": True, "maps": found_maps}
        else:
            return {"success": False, "message": "No maps found on robot."}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.route("/api/robot/maps", methods=["GET"])
def api_robot_maps():
    global found_ip
    robot_ip = found_ip
    if not robot_ip:
        discover_robot()
        robot_ip = found_ip
    if not robot_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    result = get_robot_maps(robot_ip)
    return jsonify(result)

# Manual override to set/validate robot IP
@app.route("/api/robot/set_ip", methods=["POST"])
def api_robot_set_ip():
    global found_ip
    try:
        data = request.get_json() or {}
        ip = data.get("ip")
        port = int(data.get("port", 5000))
        if not ip:
            return jsonify({"success": False, "message": "Missing 'ip'"}), 400
        if not validate_robot_ip(ip, ws_port=port):
            return jsonify({"success": False, "message": "Validation failed for provided IP"}), 400
        found_ip = ip
        return jsonify({"success": True, "robot_ip": found_ip, "message": "Robot IP set and validated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


USERNAME = "linaro"  # Replace with your robot's SSH username
PASSWORD = "linaro"  # Replace with the correct password

def check_storage(ip, username, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=username, password=password)

    stdin, stdout, stderr = ssh.exec_command("df -h /")
    output = stdout.read().decode()
    ssh.close()

    if output:
        lines = output.strip().split("\n")
        if len(lines) >= 2:
            # Extract columns from the second line
            parts = lines[1].split()
            if len(parts) >= 5:
                total = parts[1]       # Total size
                used = parts[2]        # Used (optional)
                free = parts[3]        # Free space
                percent = parts[4]     # Usage percentage
                return total, free, percent

    return None, None, None

# --- Relocation logic (from relocate.py, simplified) ---
def force_relocate_ws(robot_ip, x, y, theta, mode=0):
    try:
        ws = websocket.create_connection(f"ws://{robot_ip}:5000")
        ws.settimeout(10)
        ws.send(json.dumps({
            "cmd": "request_force_relocate",
            "data": {
                "x": x,
                "y": y,
                "theta": theta,
                "mode": mode
            }
        }))
        start_time = time.time()
        while time.time() - start_time < 10:
            try:
                res = ws.recv()
                data = json.loads(res)
                if data.get("cmd") == "response_relocate_position" and data.get("code") in [0, 1001]:
                    ws.close()
                    return True, "Relocation started successfully."
            except Exception:
                continue
        ws.close()
        return False, "Relocation failed or timed out."
    except Exception as e:
        return False, str(e)

@app.route("/api/robot/relocate", methods=["POST"])
def api_robot_relocate():
    global found_ip
    robot_ip = found_ip
    if not robot_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    data = request.get_json() or {}
    x = data.get("x", 0.0)
    y = data.get("y", 0.0)
    theta = data.get("theta", 0.0)
    mode = data.get("mode", 0)
    success, message = force_relocate_ws(robot_ip, x, y, theta, mode)
    return jsonify({"success": success, "message": message})

@app.route("/api/robot/force_relocate", methods=["POST"])
def api_robot_force_relocate():
    # For now, same as relocate (could be extended for different logic)
    return api_robot_relocate()

@app.route("/api/robot/emergency_status", methods=["GET"])
def api_robot_emergency_status():
    global found_ip, found_port
    if not found_ip:
        discover_robot()
    if not found_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    try:
        ws = websocket.create_connection(f"ws://{found_ip}:{found_port or 5000}")
        ws.send(json.dumps({"cmd": "get_emr_status"}))
        res = ws.recv()
        ws.close()
        data = json.loads(res)
        if data.get("cmd") == "notify_emr_status":
            return jsonify({
                "success": True,
                "status": data.get("data", {}).get("status", 0),
                "msg": data.get("msg", ""),
            })
        else:
            return jsonify({"success": False, "message": "Unexpected response", "raw": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/robot/storage", methods=["GET"])
def api_robot_storage():
    global found_ip
    robot_ip = found_ip
    if not robot_ip:
        discover_robot()
        robot_ip = found_ip
    if not robot_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    
    try:
        total, free, percent = check_storage(robot_ip, USERNAME, PASSWORD)
        if total is not None:
            return jsonify({
                "success": True,
                "total": total,
                "free": free,
                "percent": percent,
                "message": "Storage information retrieved successfully"
            })
        else:
            return jsonify({"success": False, "message": "Failed to retrieve storage information"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    

@app.route("/api/robot/execute", methods=["POST"])
def api_robot_execute():
    global found_ip, found_port
    data = request.get_json()
    stitched_map_ids = data.get("stitchedMapIds", [])
    charge_map_id = data.get("chargeMapId", "be6e76e5-3612-4eb7-89ee-6bc09f222634")
    if not stitched_map_ids:
        return jsonify({"success": False, "message": "No map IDs provided."}), 400
    if not found_ip:
        discover_robot()
    if not found_ip:
        return jsonify({"success": False, "message": "Robot not found or not connected."}), 404
    if not found_port:
        found_port = 5000  # fallback to default if not found
    if not charge_map_id:
        return jsonify({"success": False, "message": "No charge map ID provided."}), 400

    try:
        # This function checks battery before navigation and charges if needed
        result = run_multi_map_navigation_with_charging(
            found_ip, stitched_map_ids, charge_map_id, found_port,
            navigation_status=navigation_status,
            navigation_control=navigation_control
        )
        if result.get("success"):
            return jsonify({"success": True, "message": "Navigation completed"})
        else:
            return jsonify({"success": False, "message": result.get("message", "Navigation failed")})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


if __name__ == "__main__":
    app.run(debug=True)