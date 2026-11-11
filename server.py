"""
Project ARCANE - Backend Controller
Author: Ragnork Nectar (Yashveer Gaur)
Description: Local PC Command Center (Flask Backend)
"""

import os
import sys
import socket
import subprocess
import platform
import getpass
import time
import threading
from datetime import datetime

import psutil
import requests
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

IS_WINDOWS = platform.system().lower() == "windows"
APP_BASE = os.path.dirname(os.path.abspath(__file__))
active_pings = {}

def run_cmd(cmd, shell=True, timeout=10):
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "code": -1}

def get_public_ip():
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
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

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

        return jsonify({
            "cpu": {"percent": cpu_percent, "cores": cpu_count},
            "ram": {"percent": ram.percent, "used_gb": round(ram.used / (1024**3), 2), "total_gb": round(ram.total / (1024**3), 2)},
            "disk": {"percent": disk.percent, "used_gb": round(disk.used / (1024**3), 2), "total_gb": round(disk.total / (1024**3), 2)},
            "uptime": {"seconds": uptime_seconds, "formatted": str(datetime.utcfromtimestamp(uptime_seconds) - datetime.utcfromtimestamp(0)).split(".")[0]},
            "os": {"system": platform.system(), "hostname": socket.gethostname(), "username": getpass.getuser()},
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        "desktop": os.path.join(user_home, "Desktop"),
        "project": APP_BASE,
    }
    if folder not in folders:
        return jsonify({"success": False, "message": f"Unknown folder: {folder}"}), 400
    path = folders[folder]
    try:
        if not os.path.exists(path): return jsonify({"success": False, "message": f"Path not found: {path}"}), 404
        os.startfile(path)
        return jsonify({"success": True, "message": f"Opened: {path}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/net/info")
def net_info():
    try:
        return jsonify({"hostname": socket.gethostname(), "private_ip": get_private_ip(), "public_ip": get_public_ip()})
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
                    devices.append({"ip": parts[0], "mac": parts[1] if len(parts) > 1 else "N/A", "type": parts[2] if len(parts) > 2 else "dynamic"})
        return jsonify({"devices": devices, "count": len(devices)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/net/ping", methods=["POST"])
def ping_target():
    data = request.get_json() or {}
    target = data.get("target", "").strip()
    if not target: return jsonify({"success": False, "message": "Target missing"}), 400
    cmd = f"ping -n 1 -w 2000 {target}" if IS_WINDOWS else f"ping -c 1 -W 2 {target}"
    result = run_cmd(cmd, timeout=6)
    output = result["stdout"]
    latency = None
    if "time=" in output:
        try: latency = output.split("time=")[1].split("ms")[0].strip()
        except: pass
    elif "time<" in output:
        try: latency = "<" + output.split("time<")[1].split("ms")[0].strip()
        except: pass
    return jsonify({"success": result["code"] == 0, "alive": result["code"] == 0, "target": target, "latency": latency if latency is not None else "N/A"})

@app.route("/api/net/portscan", methods=["POST"])
def port_scan():
    data = request.get_json() or {}
    target = data.get("target", "").strip()
    start_port = int(data.get("start", 1))
    end_port = int(data.get("end", 100))
    if not target: return jsonify({"success": False, "message": "Target missing"}), 400
    if start_port < 1 or end_port > 65535 or start_port > end_port: return jsonify({"success": False, "message": "Invalid port range"}), 400
    if end_port - start_port > 500: return jsonify({"success": False, "message": "Range too large (max 500)."}), 400

    open_ports = []
    start_time = time.time()
    for port in range(start_port, end_port + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        try:
            if sock.connect_ex((target, port)) == 0: open_ports.append(port)
        except: pass
        finally: sock.close()
    elapsed = round(time.time() - start_time, 2)
    return jsonify({"success": True, "target": target, "scanned": end_port - start_port + 1, "open_ports": open_ports, "elapsed_sec": elapsed})

@app.route("/api/power", methods=["POST"])
def power_control():
    data = request.get_json() or {}
    action = data.get("action", "").lower()
    code = data.get("code", "").strip()
    if code != "ARCANE-77": return jsonify({"success": False, "message": "ACCESS CODE REJECTED."}), 403

    commands = {
        "lock": "rundll32.exe user32.dll,LockWorkStation",
        "shutdown": "shutdown /s /t 5",
        "restart": "shutdown /r /t 5",
        "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
    }
    if action not in commands: return jsonify({"success": False, "message": f"Unknown action"}), 400
    run_cmd(commands[action], timeout=5)
    return jsonify({"success": True, "message": f"Command '{action}' dispatched to OS."})

# ============ NAYA ROUTE: TERMINAL HUB ============
@app.route("/api/terminal/run", methods=["POST"])
def terminal_run():
    data = request.get_json() or {}
    term = data.get("terminal", "").lower()
    cmd_text = data.get("command", "").strip()

    if term == "cmd":
        # CMD normal pop-up (run command then pause)
        if cmd_text:
            os.system(f'start cmd /k "{cmd_text}"')
        else:
            os.system('start cmd')
        return jsonify({"success": True, "message": "CMD launched."})
    
    elif term == "admin":
        # Run CMD as Admin (Windows UAC prompt aayega)
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/k {cmd_text}" if cmd_text else "", None, 1)
            return jsonify({"success": True, "message": "Admin CMD launch sequence initiated."})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
            
    elif term in ["kali", "ubuntu"]:
        # WSL Terminal launch with command
        wsl_distro = "kali-linux" if term == "kali" else "Ubuntu"
        
        # Windows Terminal (wt) check
        has_wt = subprocess.run("where wt", shell=True, capture_output=True).returncode == 0
        
        if has_wt:
            # Agar Windows Terminal hai toh usko use karo (zyada accha dikhta hai)
            if cmd_text:
                os.system(f'wt -w 0 wsl -d {wsl_distro} bash -c "{cmd_text}; exec bash"')
            else:
                os.system(f'wt -w 0 wsl -d {wsl_distro}')
        else:
            # Fallback to normal cmd -> wsl
            if cmd_text:
                os.system(f'start cmd /k wsl -d {wsl_distro} bash -c "{cmd_text}; bash"')
            else:
                os.system(f'start cmd /k wsl -d {wsl_distro}')
                
        return jsonify({"success": True, "message": f"{term.upper()} WSL Terminal launched."})
    
    return jsonify({"success": False, "message": "Unknown terminal"}), 400


if __name__ == "__main__":
    print("=" * 60)
    print("  PROJECT ARCANE :: PC Command Center (Backend)")
    print("  Listening on: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)