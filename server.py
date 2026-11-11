"""
Project ARCANE - Backend Controller
Author: Ragnork Nectar (Yashveer Gaur)
Description: Local PC Command Center (Flask Backend)
"""

# ============ STANDARD LIBRARY IMPORTS ============
import os
import sys
import socket
import subprocess
import platform
import getpass
import time
import threading
from datetime import datetime

# ============ THIRD PARTY IMPORTS ============
import psutil
import requests
from flask import Flask, render_template, jsonify, request

# ============ FLASK APP INIT ============
app = Flask(__name__)

# ============ CONFIG ============
IS_WINDOWS = platform.system().lower() == "windows"
APP_BASE = os.path.dirname(os.path.abspath(__file__))

# In-memory store (baad me kaam aayega)
active_pings = {}


# ============ HELPER FUNCTIONS ============

def run_cmd(cmd, shell=True, timeout=10):
    """Run a shell command safely and return output."""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "code": -1}


def get_public_ip():
    """Fetch public WAN IP."""
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        return r.json().get("ip", "Unknown")
    except Exception:
        try:
            r = requests.get("https://ifconfig.me/ip", timeout=5)
            return r.text.strip()
        except Exception:
            return "Offline / Unknown"


def get_private_ip():
    """Fetch local private IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ============ ROUTES ============

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/system/stats")
def system_stats():
    try:
        cpu_percent = psutil.cpu_percent(interval=0.3)
        cpu_count = psutil.cpu_count(logical=True)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)

        battery = psutil.sensors_battery()
        battery_info = {
            "present": battery is not None,
            "percent": round(battery.percent, 1) if battery else None,
            "plugged": battery.power_plugged if battery else None,
            "secsleft": battery.secsleft if battery else None,
        }

        return jsonify({
            "cpu": {"percent": cpu_percent, "cores": cpu_count},
            "ram": {
                "percent": ram.percent,
                "used_gb": round(ram.used / (1024**3), 2),
                "total_gb": round(ram.total / (1024**3), 2)
            },
            "disk": {
                "percent": disk.percent,
                "used_gb": round(disk.used / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2)
            },
            "uptime": {
                "seconds": uptime_seconds,
                "formatted": str(datetime.utcfromtimestamp(uptime_seconds) - datetime.utcfromtimestamp(0)).split(".")[0]
            },
            "battery": battery_info,
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "hostname": socket.gethostname(),
                "username": getpass.getuser()
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/system/processes")
def list_processes():
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"] or "Unknown",
                    "user": info["username"] or "N/A",
                    "cpu": round(info["cpu_percent"] or 0, 2),
                    "mem": round(info["memory_percent"] or 0, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: (x["cpu"], x["mem"]), reverse=True)
        return jsonify({"processes": procs[:40]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/system/kill", methods=["POST"])
def kill_process():
    data = request.get_json() or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "message": "PID missing"}), 400
    try:
        p = psutil.Process(int(pid))
        pname = p.name()
        p.terminate()
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            p.kill()
        return jsonify({"success": True, "message": f"Process {pname} (PID {pid}) terminated."})
    except psutil.NoSuchProcess:
        return jsonify({"success": False, "message": "Process not found."}), 404
    except psutil.AccessDenied:
        return jsonify({"success": False, "message": "Access denied. Run as Administrator."}), 403
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/launch/app", methods=["POST"])
def launch_app():
    data = request.get_json() or {}
    app_key = data.get("app", "").lower()

    launchers = {
        "minecraft": 'start "" cmd /c start sklauncher',
        "spotify": 'start "" spotify:',
        "steam": 'start "" steam://open/main',
        "taskmgr": 'start "" taskmgr',
        "cmd": 'start "" cmd',
        "notepad": 'start "" notepad',
        "calc": 'start "" calc',
        "explorer": 'start "" explorer',
    }

    if app_key not in launchers:
        return jsonify({"success": False, "message": f"Unknown app: {app_key}"}), 400

    run_cmd(launchers[app_key])
    return jsonify({"success": True, "message": f"Launch command sent for {app_key}."})


@app.route("/api/launch/folder", methods=["POST"])
def launch_folder():
    data = request.get_json() or {}
    folder = data.get("folder", "").lower()

    user_home = os.path.expanduser("~")
    folders = {
        "downloads": os.path.join(user_home, "Downloads"),
        "documents": os.path.join(user_home, "Documents"),
        "desktop": os.path.join(user_home, "Desktop"),
        "pictures": os.path.join(user_home, "Pictures"),
        "project": APP_BASE,
    }

    if folder not in folders:
        return jsonify({"success": False, "message": f"Unknown folder: {folder}"}), 400

    path = folders[folder]
    try:
        if not os.path.exists(path):
            return jsonify({"success": False, "message": f"Path not found: {path}"}), 404
        if IS_WINDOWS:
            os.startfile(path)
        elif platform.system().lower() == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return jsonify({"success": True, "message": f"Opened: {path}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/net/info")
def net_info():
    try:
        return jsonify({
            "hostname": socket.gethostname(),
            "private_ip": get_private_ip(),
            "public_ip": get_public_ip()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/net/scan")
def net_scan():
    try:
        result = run_cmd("arp -a", timeout=15)
        devices = []
        if result["success"]:
            for line in result["stdout"].splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].count(".") == 3:
                    devices.append({
                        "ip": parts[0],
                        "mac": parts[1] if len(parts) > 1 else "N/A",
                        "type": parts[2] if len(parts) > 2 else "dynamic"
                    })
        return jsonify({"devices": devices, "count": len(devices)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/net/ping", methods=["POST"])
def ping_target():
    data = request.get_json() or {}
    target = data.get("target", "").strip()
    if not target:
        return jsonify({"success": False, "message": "Target missing"}), 400

    cmd = f"ping -n 1 -w 2000 {target}" if IS_WINDOWS else f"ping -c 1 -W 2 {target}"
    result = run_cmd(cmd, timeout=6)
    output = result["stdout"]

    latency = None
    if "time=" in output:
        try:
            latency = output.split("time=")[1].split("ms")[0].strip()
        except Exception:
            pass
    elif "time<" in output:
        try:
            latency = "<" + output.split("time<")[1].split("ms")[0].strip()
        except Exception:
            pass

    return jsonify({
        "success": result["code"] == 0,
        "alive": result["code"] == 0,
        "target": target,
        "latency": latency if latency is not None else "N/A",
        "raw": output
    })


@app.route("/api/net/portscan", methods=["POST"])
def port_scan():
    data = request.get_json() or {}
    target = data.get("target", "").strip()
    start_port = int(data.get("start", 1))
    end_port = int(data.get("end", 100))

    if not target:
        return jsonify({"success": False, "message": "Target missing"}), 400
    if start_port < 1 or end_port > 65535 or start_port > end_port:
        return jsonify({"success": False, "message": "Invalid port range"}), 400
    if end_port - start_port > 500:
        return jsonify({"success": False, "message": "Range too large (max 500 ports)."}), 400

    open_ports = []
    start_time = time.time()

    for port in range(start_port, end_port + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        try:
            if sock.connect_ex((target, port)) == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            sock.close()

    elapsed = round(time.time() - start_time, 2)
    return jsonify({
        "success": True,
        "target": target,
        "scanned": end_port - start_port + 1,
        "open_ports": open_ports,
        "elapsed_sec": elapsed
    })


@app.route("/api/power", methods=["POST"])
def power_control():
    data = request.get_json() or {}
    action = data.get("action", "").lower()
    code = data.get("code", "").strip()

    if code != "ARCANE-77":
        return jsonify({"success": False, "message": "ACCESS CODE REJECTED."}), 403

    commands = {
        "lock": "rundll32.exe user32.dll,LockWorkStation" if IS_WINDOWS else "loginctl lock-session",
        "shutdown": "shutdown /s /t 5" if IS_WINDOWS else "shutdown -h +1",
        "restart": "shutdown /r /t 5" if IS_WINDOWS else "shutdown -r +1",
        "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0" if IS_WINDOWS else "systemctl suspend",
        "logout": "shutdown /l" if IS_WINDOWS else "gnome-session-quit --logout --no-prompt",
    }

    if action not in commands:
        return jsonify({"success": False, "message": f"Unknown action: {action}"}), 400

    run_cmd(commands[action], timeout=5)
    return jsonify({"success": True, "message": f"Command '{action}' dispatched to OS."})


# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 60)
    print("  PROJECT ARCANE :: PC Command Center (Backend)")
    print("  Listening on: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)