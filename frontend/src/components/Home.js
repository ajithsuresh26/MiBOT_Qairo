import React, { useState, useEffect } from 'react';
import { FaHdd } from "react-icons/fa";
import { FaPowerOff } from 'react-icons/fa';
import { CircularProgressbar, buildStyles } from 'react-circular-progressbar';
import 'react-circular-progressbar/dist/styles.css';
import ProgressBar from "@ramonak/react-progress-bar";
import { FaStopCircle } from 'react-icons/fa';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { GoAlertFill } from "react-icons/go";
import { FaLink } from "react-icons/fa";
import { FaWifi } from "react-icons/fa";
import { FaRobot } from "react-icons/fa";
import { FaBolt } from "react-icons/fa";



// Backend API base URL
const API_BASE_URL = 'http://localhost:5000/api';

const getColor = (percent) => {
    if (percent < 20) return '#e53935'; // red
    if (percent < 50) return '#fbc02d'; // yellow
    return 'rgb(1, 109, 57)'; // green
};

const select = ['Home', 'Maps', 'Map Stitch'];
//const images = ['/mibot.png', '/mibots.jpg', '/mibot.png', '/mibots.jpg']
const images = ['/map1.png', '/map2.png', '/map3.png', '/map4.png']

/*const maps = [
    { id: 1, name: 'mibot', image: '/mibot.png' },
    { id: 2, name: 'robot', image: '/mibots.jpg' },
    { id: 3, name: 'mibot', image: '/mibot.png' },
    { id: 4, name: 'robot', image: '/mibots.jpg' },
    { id: 5, name: 'mibot', image: '/mibot.png' },
    { id: 6, name: 'robot', image: '/mibots.jpg' },
    { id: 7, name: 'mibot', image: '/mibot.png' },
    { id: 8, name: 'robot', image: '/mibots.jpg' },
    { id: 9, name: 'robot', image: '/mibots.jpg' },
    { id: 10, name: 'robot', image: '/mibots.jpg' }

];*/



function Home() {
    const [selected, setSelected] = useState('Home');
    const [isbutton, setIsbutton] = useState(false);
    const [stitchedMapIds, setStitchedMapIds] = useState([]);
    const [networkStatus, setNetworkStatus] = useState({
        connected: false,
        name: null,
        deviceIp: null,
        loading: true
    });
    const [robotStatus, setRobotStatus] = useState({
        found: false,
        ip: null,
        wifiName: null,
        connected: false,
        loading: false
    });
    const [selectedMaps, setSelectedMaps] = useState([]);
    const [batteryStatus, setBatteryStatus] = useState({
        loading: true,
        battery: null,
        charging: null,
        error: null
    });
    const [mapsTab, setMapsTab] = useState({
        loading: false,
        maps: [],
        error: null
    });
    const [storageStatus, setStorageStatus] = useState({
    loading: true,
    total: null,
    free: null,
    percent: null,
    error: null
    });
    const [relocateLoading, setRelocateLoading] = useState(false);
    const [forceRelocateLoading, setForceRelocateLoading] = useState(false);
    const [emergencyStatus, setEmergencyStatus] = useState({ loading: true, status: 0, error: null });
    const handleQuitClick = async () => {
        if (!robotStatus.connected) {
            toast.warning("Robot not connected!");
            return;
        }
        try {
            const res = await fetch(`${API_BASE_URL}/robot/quit`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: "quit" })
            });
            const data = await res.json();
            if (data.success) {
                toast.success(data.message || "Quit command sent");
            } else {
                toast.error(data.message || "Failed to send quit command");
            }
        } catch (err) {
            toast.error("Network error: " + err.message);
        } finally {
            setStitchedMapIds([]);
            setSelectedMaps([]);
            setIsbutton(false);
        }
    };

    const handleStopClick = async () => {
        toast.info("STOP is clicked");
        setIsbutton(false); // Change to CONTINUE button
        if (!robotStatus.connected) {
            toast.warning("Robot not connected!");
            return;
        }
        try {
            const res = await fetch(`${API_BASE_URL}/robot/stop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });
            const data = await res.json();
            if (data.success) {
                toast.success(data.message || "Robot navigation stopped");
            } else {
                toast.error(data.message || "Failed to stop robot");
            }
        } catch (err) {
            toast.error("Network error: " + err.message);
        }
    };

    const handleContinueClick = async () => {
        toast.info("CONTINUE is clicked");
        if (!robotStatus.connected) {
            toast.warning("Robot not connected!");
            return;
        }
        try {
            const res = await fetch(`${API_BASE_URL}/robot/resume`, {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });
            const data = await res.json();
            if (data.success) {
                toast.success(data.message || "Robot navigation resumed");
                setIsbutton(true); // Only set to STOP if resume succeeded
            } else {
                toast.error(data.message || "Failed to resume navigation");
                setIsbutton(false); // Stay on CONTINUE if resume failed
            }
        } catch (err) {
            toast.error("Network error: " + err.message);
            setIsbutton(false);
        }
    };
    const handleSelectAll = () => {
        // Select all maps in the Map Stitch tab
        const allMaps = mapsTab.maps.map((map, idx) => ({
            id: map.id,
            image: images[idx % images.length],
            name: map.name
        }));
        setSelectedMaps(allMaps);
        console.log("selected");
    };

    const handleDeselectAll = () => {
        // Deselect all maps
        setSelectedMaps([]);
        console.log("deselected");
    };
 
    
    // For Execute button, send stitchedMapIds
    const handleExecuteClick = async () => {
        console.log("stitchedMapIds:", stitchedMapIds);
        if (!stitchedMapIds.length) {
            toast.warning("Stitch map and then execute");
            return;
        }
        if (!isbutton) setIsbutton(true);

            try {
            const res = await fetch(`${API_BASE_URL}/robot/execute`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ stitchedMapIds })
            });
            const data = await res.json();
            if (data.success) {
                toast.success(data.message || "Navigation started");
                setIsbutton(true); // Only set to STOP if navigation started
            } else {
                toast.error(data.message || "Navigation failed");
                setIsbutton(false); // Stay on CONTINUE if navigation failed
            }
        } catch (err) {
            toast.error("Network error: " + err.message);
            setIsbutton(false);
        } finally {
            setStitchedMapIds([]);
            setSelectedMaps([]);
            // Do NOT reset isbutton here!
        }
    };
    const handleRelocation = async () => {
    setRelocateLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/robot/relocate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}) // Optionally pass x, y, theta, mode
        });
        const data = await response.json();
        if (data.success) {
            toast.success(data.message || 'Relocation successful');
        } else {
            toast.error(data.message || 'Relocation failed');
        }
    } catch (error) {
        toast.error('Relocation failed');
    } finally {
        setRelocateLoading(false);
    }
};

    const handleForceRelocation = async () => {
        setForceRelocateLoading(true);
        try {
            const response = await fetch(`${API_BASE_URL}/robot/force_relocate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}) // Optionally pass x, y, theta, mode
            });
            const data = await response.json();
            if (data.success) {
                toast.success(data.message || 'Force relocation successful');
            } else {
                toast.error(data.message || 'Force relocation failed');
            }
        } catch (error) {
            toast.error('Force relocation failed');
        } finally {
            setForceRelocateLoading(false);
        }
    };

    // ...existing code...
    const fetchStorageStatus = async () => {
    setStorageStatus({ loading: true, total: null, free: null, percent: null, error: null });
    try {
        const response = await fetch(`${API_BASE_URL}/robot/storage`);
        const data = await response.json();
        if (data.success) {
            setStorageStatus({
                loading: false,
                total: data.total,
                free: data.free,
                percent: data.percent,
                error: null
            });
        } else {
            setStorageStatus({
                loading: false,
                total: null,
                free: null,
                percent: null,
                error: data.message || 'Failed to get storage status.'
            });
        }
    } catch (error) {
        setStorageStatus({
            loading: false,
            total: null,
            free: null,
            percent: null,
            error: 'Failed to get storage status.'
        });
    }
};
    // Fetch network status
    const fetchNetworkStatus = async () => {
        try {
            setNetworkStatus(prev => ({ ...prev, loading: true }));
            const response = await fetch(`${API_BASE_URL}/network/status`);
            const data = await response.json();
            
            if (data.success) {
                setNetworkStatus({
                    connected: data.connected,
                    name: data.network_name,
                    deviceIp: data.device_ip,
                    loading: false
                });
            } else {
                setNetworkStatus({
                    connected: false,
                    name: null,
                    deviceIp: null,
                    loading: false
                });
            }
        } catch (error) {
            console.error('Error fetching network status:', error);
            setNetworkStatus({
                connected: false,
                name: null,
                deviceIp: null,
                loading: false
            });
        }
    };

    // Discover robot
    const discoverRobot = async () => {
        try {
            setRobotStatus(prev => ({ ...prev, loading: true }));
            const response = await fetch(`${API_BASE_URL}/robot/discover`);
            const data = await response.json();
            
            if (data.success) {
                setRobotStatus({
                    found: data.robot_found,
                    ip: data.robot_ip,
                    wifiName: data.robot_wifi_name,
                    connected: data.connected,
                    loading: false
                });
                
                if (data.robot_found) {
                    toast.success(`Robot found at ${data.robot_ip}!`);
                } else {
                    toast.warning('Robot not found on the network');
                }
            } else {
                setRobotStatus({
                    found: false,
                    ip: null,
                    wifiName: null,
                    connected: false,
                    loading: false
                });
                toast.error('Error discovering robot');
            }
        } catch (error) {
            console.error('Error discovering robot:', error);
            setRobotStatus({
                found: false,
                ip: null,
                wifiName: null,
                connected: false,
                loading: false
            });
            toast.error('Failed to discover robot');
        }
    };

    // Get comprehensive status
    const getComprehensiveStatus = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/robot/status`);
            const data = await response.json();
            
            if (data.success) {
                setNetworkStatus({
                    connected: data.device.connected,
                    name: data.device.wifi_name,
                    deviceIp: data.device.ip,
                    loading: false
                });
                
                setRobotStatus({
                    found: data.robot.found,
                    ip: data.robot.ip,
                    wifiName: data.robot.wifi_name,
                    connected: data.network.connected,
                    loading: false
                });
            }
        } catch (error) {
            console.error('Error getting comprehensive status:', error);
        }
    };

    // Fetch battery status
    const fetchBatteryStatus = async () => {
        setBatteryStatus({ loading: true, battery: null, charging: null, error: null });
        try {
            const response = await fetch(`${API_BASE_URL}/robot/battery`);
            const data = await response.json();
            if (data.success) {
                setBatteryStatus({
                    loading: false,
                    battery: data.battery,
                    charging: data.charging,
                    error: null
                });
            } else {
                setBatteryStatus({
                    loading: false,
                    battery: null,
                    charging: null,
                    error: data.message || 'Failed to get battery status.'
                });
            }
        } catch (error) {
            setBatteryStatus({
                loading: false,
                battery: null,
                charging: null,
                error: 'Failed to get battery status.'
            });
        }
    };

    // Fetch current map information
    const fetchCurrentMapInfo = async () => {
        setCurrentMapInfo(prev => ({ ...prev, loading: true, error: null }));
        try {
            const response = await fetch(`${API_BASE_URL}/robot/current_map`);
            const data = await response.json();
            if (data.success) {
                setCurrentMapInfo({
                    loading: false,
                    currentMapId: data.current_map_id,
                    currentMapName: data.current_map_name,
                    upcomingMapId1: data.upcoming_map_id_1,
                    upcomingMapName1: data.upcoming_map_name_1,
                    upcomingMapId2: data.upcoming_map_id_2,
                    upcomingMapName2: data.upcoming_map_name_2,
                    error: null
                });
            } else {
                setCurrentMapInfo(prev => ({
                    ...prev,
                    loading: false,
                    error: data.message || 'Failed to get current map info.'
                }));
            }
        } catch (error) {
            setCurrentMapInfo(prev => ({
                ...prev,
                loading: false,
                error: 'Failed to get current map info.'
            }));
        }
    };
    
    useEffect(() => {
    let interval = null;
    const fetchEmergencyStatus = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/robot/emergency_status`);
            const data = await res.json();
            if (data.success) {
                setEmergencyStatus({ loading: false, status: data.status, error: null });
            } else {
                setEmergencyStatus({ loading: false, status: 0, error: data.message || "Failed to get status" });
            }
        } catch (err) {
            setEmergencyStatus({ loading: false, status: 0, error: "Failed to get status" });
        }
    };
    fetchEmergencyStatus();
    interval = setInterval(fetchEmergencyStatus, 2000); // poll every 3 seconds
    return () => clearInterval(interval);
}, []);
    // Fetch network status once on mount; no auto-refresh
    useEffect(() => {
        fetchNetworkStatus();
    }, []);

    // Refresh robot status when network status changes
    useEffect(() => {
        if (networkStatus.connected) {
            getComprehensiveStatus();
        }
    }, [networkStatus.connected]);

    // Fetch battery status when robotStatus changes or every 30s if robot is found
    useEffect(() => {
        if (robotStatus.found) {
            fetchBatteryStatus();
            const interval = setInterval(fetchBatteryStatus, 30000);
            return () => clearInterval(interval);
        }
    }, [robotStatus.found, robotStatus.ip]);

    // Fetch current map info when navigation is active
    useEffect(() => {
        if (robotStatus.connected && isbutton) {
            fetchCurrentMapInfo();
            const interval = setInterval(fetchCurrentMapInfo, 2000); // Update every 2 seconds
            return () => clearInterval(interval);
        } else {
            // Clear map info when not navigating
            setCurrentMapInfo({
                loading: false,
                currentMapId: null,
                currentMapName: null,
                upcomingMapId1: null,
                upcomingMapName1: null,
                upcomingMapId2: null,
                upcomingMapName2: null,
                error: null
            });
        }
    }, [robotStatus.connected, isbutton]);

        // ...existing code...
    useEffect(() => {
        fetchStorageStatus();
        const interval = setInterval(fetchStorageStatus, 30000);
        return () => clearInterval(interval);
    }, []);
    // ...existing code...

    // Fetch maps from robot when Maps tab is selected
    useEffect(() => {
        if (selected === 'Maps') {
            setMapsTab({ loading: true, maps: [], error: null });
            fetch(`${API_BASE_URL}/robot/maps`)
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        setMapsTab({ loading: false, maps: data.maps, error: null });
                    } else {
                        setMapsTab({ loading: false, maps: [], error: data.message || 'No maps found.' });
                    }
                })
                .catch(() => setMapsTab({ loading: false, maps: [], error: 'Not connected to robot.' }));
        }
    }, [selected]);

    const [currentMapInfo, setCurrentMapInfo] = useState({
        loading: true,
        currentMapId: null,
        currentMapName: null,
        upcomingMapId1: null,
        upcomingMapName1: null,
        upcomingMapId2: null,
        upcomingMapName2: null,
        error: null
    });

    
    const toggleSelect = (mapId, mapImage, mapname) => {
        setSelectedMaps((prev) => {
            const exists = prev.find((m) => m.id === mapId);

            if (exists) {
                return prev.filter((m) => m.id !== mapId); // remove
            } else {
                return [...prev, { id: mapId, image: mapImage, name: mapname }]; // add
            }
        });
    };


    const handleEmergencyClick = async () => {
    try {
        const res = await fetch(`${API_BASE_URL}/robot/emergency_exit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (data.success) {
            toast.success(data.message || "Emergency exit triggered!");
        } else {
            toast.error(data.message || "Emergency exit failed!");
        }
    } catch (err) {
        toast.error("Network error: " + err.message);
    }
    };
        
    const handleChargeClick = async () => {
        if (!robotStatus.connected) {
            toast.warning("Robot not connected!");
            return;
        }
        toast.info("Navigating to charging point...");
        const res = await fetch(`${API_BASE_URL}/robot/auto_charge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (data.success) {
            toast.success(data.message || "Successfully docked to Charging point");
            fetchBatteryStatus(); // <-- add this
        } else {
            toast.error(data.message || "Could not find Charging Station!");
        }
    };
        
    const handleUndockClick = async () => {
        if (!robotStatus.connected) {
            toast.warning("Robot not connected!");
            return;
        }
        toast.info("Undocking from charging pile...");
        const res = await fetch(`${API_BASE_URL}/robot/undock`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (data.success) {
            toast.success(data.message || "Successfully undocked from Charging point");
            fetchBatteryStatus(); // <-- add this
        } else {
            toast.error(data.message || "Failed to undock from Charging Station!");
        }
    };
            
    const handleStrich = () => {
        // Extract selected map IDs
        const ids = selectedMaps.map(map => map.id);

        // Simulate a stitching process (replace with real API call if needed)
        if (ids.length > 0) {
            setStitchedMapIds(ids);
            toast.success('Map Stitched');
            console.log('Stitched Map IDs:', ids);
        } else {
            setStitchedMapIds([]);
            toast.error('No Map Selected for Stitching')
        }
    };
    

    const handleRefreshNetwork = () => {
        fetchNetworkStatus();
        toast.info('Refreshing network status...');
    };

    const handleDiscoverRobot = () => {
        discoverRobot();
    };

    const handleRefreshMapsCache = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/robot/refresh_maps_cache`, {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });
            const data = await response.json();
            if (data.success) {
                toast.success(data.message || "Maps cache refreshed successfully");
                // Refresh current map info to get updated names
                fetchCurrentMapInfo();
            } else {
                toast.error(data.message || "Failed to refresh maps cache");
            }
        } catch (error) {
            toast.error("Failed to refresh maps cache");
        }
    };

    return (
        <div className="p-3 bg-gray-100 min-h-screen ">
            <div className="flex-col bg-white p-3 rounded shadow mb-2">

                <div className="flex w-full justify-between text-sm">
                    <img
                        src="/mibot.png"
                        alt="User"
                        className="w-[110px] h-[60px]   border-gray-300 cursor-pointer"

                    />
                    {/* LEFT GROUP OF CARDS */}
                    <div className="flex space-x-6">
                        {/* Battery Status */}
                        <div className="flex items-center gap-3">
                            <div className="flex items-center bg-white shadow-md rounded-full px-4 py-2 space-x-4 w-fit">
                                {/* Circular Progress */}
                                <div style={{ width: 50, height: 50, fontWeight: 'bold' }}>
                                    <CircularProgressbar
                                        value={batteryStatus.battery !== null ? batteryStatus.battery : 0}
                                        text={batteryStatus.loading ? '...' : batteryStatus.battery !== null ? `${batteryStatus.battery}%` : 'N/A'}
                                        strokeWidth={12}
                                        styles={buildStyles({
                                            pathColor: getColor(batteryStatus.battery !== null ? batteryStatus.battery : 0),
                                            textColor: getColor(batteryStatus.battery !== null ? batteryStatus.battery : 0),
                                            trailColor: '#d6d6d6',
                                            textSize: '22px',
                                        })}
                                    />
                                </div>
                                <div className="items-center justify-center">
                                    <p className="text-sm text-gray-500">Battery Status</p>
                                    {batteryStatus.loading ? (
                                        <p className="font-semibold text-left text-black">Loading...</p>
                                    ) : batteryStatus.error ? (
                                        <p className="font-semibold text-center text-red-500">{batteryStatus.error}</p>
                                    ) : (
                                        <>
                                            <p className="font-semibold text-center text-black">{batteryStatus.battery}%</p>
                                            <div className="flex items-center gap-1 justify-center">
                                                <FaBolt className={batteryStatus.charging ? 'text-green-500' : 'text-gray-400'} />
                                                <span className={`text-xs font-semibold ${batteryStatus.charging ? 'text-green-600' : 'text-gray-600'}`}>{batteryStatus.charging ? 'Charging' : 'Not Charging'}</span>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                        
                        {/* Network Status */}
                        <div className="flex items-center ">
                            <div className="flex items-center bg-white shadow-md rounded-full px-4 py-2 space-x-4 w-fit">
                                <div className={`${networkStatus.connected ? 'bg-green-600' : 'bg-red-600'} text-white p-2 rounded-full text-lg`}>
                                    <FaWifi />
                                </div>
                                <div className="text-black">
                                    {networkStatus.loading ? (
                                        <>
                                            <p className="text-sm font-medium">Checking...</p>
                                            <p className="font-semibold text-center">Network</p>
                                        </>
                                    ) : networkStatus.connected ? (
                                        <>
                                            <p className="text-sm text-gray-500">Connected Network</p>
                                            <p className="font-semibold text-left">{networkStatus.name || 'Wi-Fi'}</p>
                                            <p className="text-xs text-gray-500 ">{networkStatus.deviceIp}</p>
                                        </>
                                    ) : (
                                        <>
                                            <p className="text-sm font-medium">Not Connected</p>
                                            <p className="font-semibold text-center text-black">Wi-Fi</p>
                                        </>
                                    )}
                                </div>
                                <button 
                                    onClick={handleRefreshNetwork}
                                    className="text-blue-600 hover:text-blue-800 text-sm"
                                    title="Refresh network status"
                                >
                                    ↻
                                </button>
                            </div>
                        </div>

                        {/* Robot Status */}
                        <div className="flex items-center ">
                            <div className="flex items-center bg-white shadow-md rounded-full px-4 py-2 space-x-4 w-fit">
                                <div className={`${robotStatus.connected ? 'bg-green-600' : robotStatus.found ? 'bg-yellow-600' : 'bg-red-600'} text-white p-2 rounded-full text-lg`}>
                                    <FaRobot />
                                </div>
                                <div className="text-black">
                                    {robotStatus.loading ? (
                                        <>
                                            <p className="text-sm font-medium">Discovering...</p>
                                            <p className="font-semibold text-center">Robot</p>
                                        </>
                                    ) : robotStatus.connected ? (
                                        <>
                                            <p className="text-sm font-medium">Robot Connected</p>
                                            <p className="font-semibold text-center">{robotStatus.ip || 'Connected'}</p>
                                        </>
                                    ) : robotStatus.found ? (
                                        <>
                                            <p className="text-sm font-medium">Robot Found</p>
                                            <p className="font-semibold text-center">{robotStatus.ip}</p>
                                        </>
                                    ) : (
                                        <>
                                            <p className="text-sm text-gray-500">Robot Not Found</p>
                                            <p className="font-semibold text-left text-black">Disconnected</p>
                                        </>
                                    )}
                                </div>
                                <button 
                                    onClick={handleDiscoverRobot}
                                    className="text-blue-600 hover:text-blue-800 text-sm"
                                    title="Discover robot"
                                >
                                    🔍
                                </button>
                            </div>
                        </div>

                        <div className="flex items-center ">
                            <div className="flex items-center bg-white shadow-md rounded-full px-4 py-2 space-x-4 w-fit">
                                <div className="text-white text-3xl rounded-full bg-blue-600 w-10 text-center h-10 flex items-center justify-center">
                                    <FaHdd />
                                </div>
                                <div className="flex-1">
                                    <div className="flex justify-between text-sm text-gray-800 w-full">
                                        <span className="font-medium text-blue-800">Disk : C</span>
                                        <span className="text-xs text-gray-500">
                                            {storageStatus.loading
                                                ? 'Loading...'
                                                : storageStatus.total !== null && storageStatus.free !== null
                                                    ? `Total: ${storageStatus.total}B | Free: ${storageStatus.free}B`
                                                    : ''}
                                        </span>
                                    </div>
                                    <div className="relative w-64 h-6 rounded-full">
                                        <ProgressBar
                                            completed={storageStatus.percent ? parseInt(storageStatus.percent) : 0}
                                            bgColor="blue"
                                            labelAlignment="center"
                                            labelColor="#fff"
                                            isLabelVisible={true}
                                            customLabel={storageStatus.loading ? '...' : `${storageStatus.percent || 0}`}
                                        />
                                    </div>
                                    {storageStatus.error && (
                                        <div className="text-xs text-red-500">{storageStatus.error}</div>
                                    )}
                                </div>
                            </div>
                        </div>
                    
                    </div>
                    {/* RIGHT: START BUTTON */}
                    <div className="flex items-center justify-center ">
                        <div className="flex flex-col items-center">
                            {/* Power Button on top center */}
                            <div className="flex flex-col items-center justify-center">
                                <button
                                    onClick={isbutton ? handleStopClick : handleContinueClick}
                                    className={`bg-gradient-to-b ${isbutton
                                        ? 'from-red-600 to-black'
                                        : 'from-[rgb(3,176,67)] to-[rgba(6,6,6,0.84)]'
                                        } rounded-xl w-[78px] h-[58px] flex flex-col items-center justify-center shadow-md`}
                                >
                                    {isbutton ? (
                                        <>
                                            <FaStopCircle className="text-2xl text-white mb-1" />
                                            <p className="text-xs text-white font-semibold">STOP</p>
                                        </>
                                    ) : (
                                        <>
                                            <FaPowerOff className="text-2xl text-white mb-1" />
                                            <p className="text-md text-white font-medium">START</p>
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>

                </div>
                <div className="flex">
                    {select.map((level, index) => (
                        <div
                            key={index}
                            className={`cursor-pointer px-4 py-2 font-semibold rounded 
              ${selected === level ? 'underline text-blue-600' : 'text-gray-600 hover:bg-gray-200'}`}
                            onClick={() => setSelected(level)}
                        >
                            {level}
                        </div>
                    ))}
                    <div className=" flex gap-3 ml-auto mt-3">

                        <ToastContainer position="top-center" autoClose={3000} />
                        
                        {batteryStatus.charging === 2 ? (
                            <button
                                onClick={handleUndockClick}
                                className="bg-black hover:bg-yellow-700 text-white px-2 py-1 font-semibold rounded shadow"
                            >
                                Undock from Charging Point
                            </button>
                        ) : (
                            <button
                                onClick={handleChargeClick}
                                className="bg-green-600 hover:bg-green-700 text-white px-2 py-1 font-semibold rounded shadow"
                            >
                                Dock to Charging Point
                            </button>
                        )}
                        
                        <button
                            onClick={handleEmergencyClick}
                            className="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-1 rounded shadow font-semibold"
                        >
                            Emergency
                        </button>
                        

                        <button
                            onClick={handleRefreshMapsCache}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1 rounded shadow font-semibold"
                        >
                            Refresh Maps
                        </button>

                        <button
                            onClick={handleQuitClick}
                            className="bg-red-600 hover:bg-red-700 text-white px-4 py-1 rounded shadow font-semibold  flex items-center"
                            //style={{ minWidth: '110px' }}
                        >
                            Quit
                        </button>
                    </div>
                </div>

            </div>
            {selected === 'Home' &&

                <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4">
                    {/* Robot Image */}
                    <div className="h-[40rem] bg-gradient-to-b from-[rgb(132,237,245)] to-white rounded overflow-hidden">

                        <img src="./loginss.png" alt="MiBot" className="w-full h-full object-cover rounded" />
                    </div>

                    <div className="grid grid-rows-1 md:grid-rows-[25%_75%] gap-6">
                        <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4 min-w-0">
                            <div className="bg-white p-4 rounded shadow">
                                <div className="flex flex-col gap-4">
                                    <h2 className="text-lg text-gray-500 font-semibold">MiBOT Qairo</h2>
                                    <p className="text-gray-500">Connected IP: {robotStatus.ip || '123.456.789'}</p>
                                    <div className="space-y-2">
                                        <p className="text-gray-500">Live Map Name:</p>
                                        {currentMapInfo.loading ? (
                                            <p className="text-sm text-blue-600">Loading...</p>
                                        ) : currentMapInfo.currentMapName ? (
                                            <p className="text-sm font-semibold text-green-600">{currentMapInfo.currentMapName}</p>
                                        ) : (
                                            <p className="text-sm text-gray-400">No active navigation</p>
                                        )}
                                        
                                        <p className="text-gray-500">Live Map ID:</p>
                                        {currentMapInfo.loading ? (
                                            <p className="text-sm text-blue-600">Loading...</p>
                                        ) : currentMapInfo.currentMapId ? (
                                            <p className="text-sm font-mono text-gray-700">{currentMapInfo.currentMapId}</p>
                                        ) : (
                                            <p className="text-sm text-gray-400">No active navigation</p>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className={`w-3 h-3 rounded-full ${robotStatus.connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                                        <span className="text-sm text-gray-600">
                                            {robotStatus.connected ? 'Connected' : 'Disconnected'}
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="bg-white p-4 rounded shadow w-full min-w-0">
                                <h2 className="text-lg text-gray-500 font-semibold">Route Mapping</h2>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4">
                                    {images.map((src, index) => (
                                        <img
                                            key={index}
                                            src={src}
                                            alt={` ${index + 1}`}
                                            className=" w-full h-20  object-cover rounded shadow"
                                        />
                                    ))}
                                </div>
                            </div>
                        </div>
                        <div className="bg-white p-2 rounded shadow h-[29rem]">

                            <div className="flex justify-between  ">
                                <h3 className="text-md font-semibold text-blue-600">Live Map Name</h3>
                                <div className="space-x-2 p-2">
                                    <button onClick={handleRelocation} className="bg-blue-700 text-white px-2 py-1 rounded text-sm" disabled={relocateLoading}>{relocateLoading ? 'Relocating...' : 'Relocation'}</button>
                                    <button onClick={handleForceRelocation} className="bg-blue-700 text-white px-2 py-1 rounded text-sm" disabled={forceRelocateLoading}>{forceRelocateLoading ? 'Relocating...' : 'Force Relocation'}</button>
                                </div>
                            </div>


                            <div className="flex flex-col md:flex-row gap-6">

                                <div className=" rounded   flex justify-center items-center p-2">
                                    <img
                                        src="./mibots.jpg"
                                        alt="MiBot"
                                        className="h-[50vh] w-[700px] object-contain rounded"
                                    />
                                </div>


                                <div className="grid grid-rows-2 w-full h-[400px] gap-3 overflow-hidden rounded-lg shadow-md">
                                    {[0, 1].map((i) => {
                                        const upcomingMapId = i === 0 ? currentMapInfo.upcomingMapId1 : currentMapInfo.upcomingMapId2;
                                        const upcomingMapName = i === 0 ? currentMapInfo.upcomingMapName1 : currentMapInfo.upcomingMapName2;
                                        
                                        return (
                                            <div
                                                key={i}
                                                className="relative flex flex-col w-full h-full overflow-hidden rounded shadow"
                                            >
                                                <img
                                                    src={images[i]}
                                                    alt={`Map ${i + 1}`}
                                                    className="h-full w-full object-fit brightness-75"
                                                />
                                                <div className="absolute top-4 left-4 text-white">
                                                    <p className="font-medium text-white">
                                                        Upcoming Map {i + 1}:
                                                    </p>
                                                    <p className="text-sm text-white">
                                                        {upcomingMapName || "None"}
                                                    </p>
                                                    <p className="text-xs text-gray-300 font-mono">
                                                        ID: {upcomingMapId || "None"}
                                                    </p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>


                            </div>
                        </div>
                    </div>

                </div>}
            {selected === 'Maps' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4">
                    {mapsTab.loading ? (
                        <div className="col-span-full flex justify-center items-center h-32">
                            <span className="text-gray-500 text-lg">Loading maps...</span>
                        </div>
                    ) : mapsTab.error ? (
                        <div className="col-span-full flex justify-center items-center h-32">
                            <span className="text-red-500 text-lg">{mapsTab.error}</span>
                        </div>
                    ) : mapsTab.maps.length === 0 ? (
                        <div className="col-span-full flex justify-center items-center h-32">
                            <span className="text-gray-500 text-lg">No maps found on robot.</span>
                        </div>
                    ) : (
                        mapsTab.maps.map((map, index) => (
                            <div key={index} className="bg-white shadow rounded p-2">
                                <div className="mt-2 text-sm">
                                    <p><strong>Map Name:</strong> {map.name}</p>
                                    <p><strong>Map ID:</strong> {map.id}</p>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            )}

            {selected === 'Map Stitch' && (
                <div className="bg-white p-4 rounded shadow">


                    <div className="flex flex-col justify-between bg-blue-50 h-[250px] gap-3 my-4 p-4 rounded">
                        {/* Button Row */}
                        <div className="flex justify-end gap-3">
                            <button
                                onClick={handleStrich} className="bg-blue-700 hover:bg-blue-900 text-white font-semibold px-4 py-2 rounded-full">
                                Stitch Map
                            </button>
                            <button
                                onClick={handleExecuteClick}
                                className="bg-blue-700 hover:bg-blue-900 text-white font-semibold px-4 py-2 rounded-full"
                            >
                                Execute
                            </button>
                        </div>

                        {/* Message at Bottom Center */}
                        {selectedMaps.length > 0 ? (
                            <div className="flex flex-cols-1 gap-4 overflow-y-hidden">
                                {selectedMaps.map((map) => (
                                    <div className='flex items-center'>
                                        <div
                                            key={map.id}
                                            className="border rounded shadow p-4 bg-white text-center w-[15rem] h-[10rem] mr-3"
                                        >
                                            <img
                                                src={map.image}
                                                alt={`Map ${map.id}`}
                                                className="w-full h-20 object-fit rounded mb-2"
                                            />
                                            <p className="text-sm font-medium">Map ID: {map.id}</p>
                                            <p className="text-sm font-medium"> Map Name : {map.name}</p>
                                        </div>

                                        <FaLink className="text-4xl text-gray-400 transform rotate-45" />


                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="w-full flex justify-center">
                                <p className="text-gray-600">Please Select Map First</p>
                            </div>
                        )}

                    </div>




                    <div className="flex justify-between items-center mb-2">
                        <h2 className="text-xl font-semibold">Map Lists</h2>
                        <div className="text-sm  flex space-x-4">
                            <button
                                onClick={handleSelectAll}
                                className="text-gray-600 hover:underline"
                            >
                                Select All
                            </button>
                            <p>|</p>
                            <button
                                onClick={handleDeselectAll}
                                className="text-gray-600 hover:underline"
                            >
                                Deselect
                            </button>
                        </div>
                    </div>

                    {/* Map Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {mapsTab.maps.map((map, idx) => {
                            // Use idx to pick an image if needed
                            const image = images[idx % images.length]; // cycle through your images array
                            const isSelected = selectedMaps.some((selected) => selected.id === map.id);
                            const selectionIndex = selectedMaps.findIndex((selected) => selected.id === map.id) + 1;

                            return (
                                <div
                                    key={map.id}
                                    onClick={() => toggleSelect(map.id, image, map.name)}
                                    className="border shadow cursor-pointer rounded overflow-hidden shadow p-2"
                                >
                                    <div className='relative'>
                                        <img
                                            src={image}
                                            alt={map.name}
                                            className={`w-full h-32 object-cover transition duration-200 ${isSelected ? 'brightness-50' : ''}`}
                                        />
                                        {isSelected && (
                                            <div className="absolute inset-0 flex items-center justify-center">
                                                <span className="text-white text-4xl font-bold">{selectionIndex}</span>
                                            </div>
                                        )}
                                    </div>
                                    <p className="text-sm font-medium"> Map Name : {map.name}</p>
                                    <p className="text-xs text-gray-600">Map ID: {map.id}</p>
                                </div>
                            );
                        })}
                    </div>

                </div>
            )}

        {emergencyStatus.status === 1 && (
            <div
                style={{
                position: 'fixed',
                zIndex: 10000,
                top: 0,
                left: 0,
                width: '100vw',
                height: '100vh',
                background: 'rgba(0,0,0,0.7)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
                }}
            >
                <div
                style={{
                    background: 'white',
                    borderRadius: '1rem',
                    padding: '2.5rem 2rem',
                    boxShadow: '0 4px 32px rgba(0,0,0,0.3)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    minWidth: 350
                }}
                >
                <GoAlertFill className="text-5xl text-red-600 mb-4" />
                <h2 className="text-2xl font-bold text-red-700 mb-2 text-center">EMERGENCY STOP ACTIVE</h2>
                <p className="text-gray-700 text-center mb-4">
                    Please remove the emergency stop to continue using the robot web interface.
                </p>
                <button
                    onClick={() => window.location.reload()}
                    className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded font-semibold mt-2"
                >
                    Refresh
                </button>
                </div>
            </div>
            )}

        </div >


    )
}

export default Home