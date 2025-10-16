import socket
import threading
import subprocess
import platform
import requests
import json
import time

ROBOT_PORT = 5000
SUBNET_PREFIX = "192.168.0."
found_ip = None
device_wifi_name = None
device_ip = None

def get_device_wifi_info():
    """Get current device's WiFi name and IP address"""
    global device_wifi_name, device_ip
    
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
                            device_wifi_name = line.split(':', 1)[1].strip()
                            print(f"✅ WiFi name found: {device_wifi_name}")
                            break
                        # Alternative pattern
                        elif 'Profile' in line and ':' in line:
                            potential_name = line.split(':', 1)[1].strip()
                            if potential_name and potential_name != "":
                                device_wifi_name = potential_name
                                print(f"✅ WiFi profile found: {device_wifi_name}")
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

def get_robot_wifi_info(robot_ip):
    """Enhanced robot WiFi information retrieval"""
    print(f"🔍 Attempting to get WiFi info from robot at {robot_ip}...")
    
    # First, test what ports are available
    open_ports = test_robot_connection(robot_ip)
    
    # Try HTTP endpoints on discovered ports
    http_ports = [port for port in open_ports if port in [80, 8080, 3000, 8000, 9090]]
    if not http_ports:
        http_ports = [8080, 80, 3000]  # Default fallback
    
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
                        # Try to parse as plain text
                        text = response.text
                        print(f"      Response (text): {text[:200]}...")
                        # Look for common patterns in text responses
                        if 'ssid' in text.lower() or 'wifi' in text.lower():
                            print(f"      ⚠️ Found text response with WiFi info, but couldn't parse")
                        
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
        sock.send(b"GET /info HTTP/1.1\r\nHost: " + robot_ip.encode() + b"\r\n\r\n")
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
        print(f"✅ Robot found at {ip}")
        found_ip = ip
        s.close()
    except:
        pass

def main():
    print("🔍 Starting enhanced robot discovery and network verification...\n")
    
    # Get device WiFi information
    get_device_wifi_info()
    
    if device_wifi_name and device_ip:
        print(f"📱 Device Info:")
        print(f"   WiFi Name: {device_wifi_name}")
        print(f"   IP Address: {device_ip}\n")
    else:
        print("❌ Could not get device WiFi information\n")
    
    # Scan for robot
    print("🔍 Scanning for robot...")
    threads = []
    for i in range(1, 255):
        ip = f"{SUBNET_PREFIX}{i}"
        t = threading.Thread(target=check_ip, args=(ip,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    if found_ip:
        print(f"\n🤖 Robot found at: {found_ip}")
        
        # Check if they're on the same subnet
        if device_ip:
            same_network = check_same_network(device_ip, found_ip)
        
        # Get robot WiFi information with enhanced methods
        robot_wifi_name, robot_ip = get_robot_wifi_info(found_ip)
        
        if robot_wifi_name:
            print(f"\n🤖 Robot Info:")
            print(f"   WiFi Name: {robot_wifi_name}")
            print(f"   IP Address: {robot_ip}\n")
            
            # Compare networks
            if device_wifi_name and robot_wifi_name:
                if device_wifi_name == robot_wifi_name:
                    print("✅ CONNECTED: Both device and robot are on the same WiFi network!")
                    print(f"   Network: {device_wifi_name}")
                    print(f"   Device IP: {device_ip}")
                    print(f"   Robot IP: {found_ip}")
                else:
                    print("❌ NOT CONNECTED: Device and robot are on different networks!")
                    print(f"   Device WiFi: {device_wifi_name}")
                    print(f"   Robot WiFi: {robot_wifi_name}")
                    print("   Please connect both to the same WiFi network.")
            else:
                print("⚠️  Could not verify WiFi network names.")
                print("   Please check manually that both devices are on the same network.")
        else:
            print("\n⚠️  Could not get robot's WiFi information from API calls.")
            if device_ip and found_ip:
                if check_same_network(device_ip, found_ip):
                    print("   However, both devices appear to be on the same subnet.")
                    print("   This suggests they're likely on the same network.")
                    print(f"   Device: {device_ip} (WiFi: {device_wifi_name})")
                    print(f"   Robot: {found_ip}")
                    print("   ✅ You should be able to connect!")
                else:
                    print("   And they appear to be on different subnets.")
            else:
                print(f"   You can try connecting to: {found_ip}")
    else:
        print("❌ Robot not found on the network.")
        if device_wifi_name:
            print(f"   Make sure robot is connected to: {device_wifi_name}")
        print("\n🔍 Troubleshooting tips:")
        print("   1. Ensure the robot is powered on and connected to WiFi")
        print("   2. Check if the robot is on a different subnet")
        print("   3. Verify the robot is listening on port 5000")
        print("   4. Try scanning a different IP range if needed")

if __name__ == "__main__":
    main()