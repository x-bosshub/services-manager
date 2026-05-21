from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import psutil
import os
import signal
import subprocess
import re
import secrets
import time
from datetime import timedelta, datetime
from dotenv import load_dotenv

# โหลดตัวแปรตั้งค่าจากไฟล์ .env
load_dotenv()

app = Flask(__name__)

# 1. จัดการ Secret Key สำหรับ Session
SECRET_FILE = 'secret.key'
if os.path.exists(SECRET_FILE):
    with open(SECRET_FILE, 'rb') as f:
        app.secret_key = f.read()
else:
    new_key = secrets.token_bytes(32)
    with open(SECRET_FILE, 'wb') as f:
        f.write(new_key)
    app.secret_key = new_key

# 2. บังคับให้ Session หมดอายุภายใน 60 นาที
app.permanent_session_lifetime = timedelta(minutes=60)

# 3. ดึงการตั้งค่าจากไฟล์ .env (หากไม่มีให้ใช้ค่าเริ่มต้นเป็น admin1234)
DEFAULT_PASSWORD = os.environ.get('DASHBOARD_PASS', 'admin1234')
DEBUG_APP = os.environ.get('DEBUG_APP', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 8000))

def format_uptime(seconds):
    """แปลงวินาทีให้อยู่ในรูปแบบ วัน ชม. นาที ที่อ่านง่าย"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} วัน")
    if hours > 0 or days > 0:
        parts.append(f"{hours} ชม.")
    parts.append(f"{minutes} นาที")
    return " ".join(parts)

def get_service_name(pid):
    """เช็กว่า PID นี้เป็น Systemd Service หรือไม่"""
    try:
        with open(f'/proc/{pid}/cgroup', 'r') as f:
            content = f.read()
            match = re.search(r'/([^/]+\.service)', content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None

def get_docker_container_by_port(target_port):
    """หาชื่อ Docker Container จาก Port ที่กำลังรัน"""
    try:
        result = subprocess.run(['docker', 'ps', '--format', '{{.Names}}|{{.Ports}}'], capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if not line or '|' not in line:
                continue
            name, ports = line.split('|', 1)
            if re.search(r':' + str(target_port) + r'->', ports):
                return name
    except Exception:
        pass
    return None

def get_ports_data():
    ports_list = []
    seen = set()
    current_time = time.time()
    try:
        connections = psutil.net_connections(kind='inet')
        listen_conns = [c for c in connections if c.status == psutil.CONN_LISTEN and c.pid]
        listen_conns.sort(key=lambda x: x.laddr.port)

        for conn in listen_conns:
            port = conn.laddr.port
            if port == 22: # ป้องกันการปิด Port SSH
                continue
                
            ip = conn.laddr.ip
            pid = conn.pid
            
            unique_key = f"{port}-{pid}"
            if unique_key in seen:
                continue
            seen.add(unique_key)
            
            service_name = get_service_name(pid)
            container_name = None
            cpu_usage = 0.0
            ram_usage_mb = 0.0
            uptime_str = "N/A"
            
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
                cmdline = proc.cmdline()
                cmd_str = " ".join(cmdline) if cmdline else "N/A"
                cwd = proc.cwd()
                
                try:
                    cpu_usage = proc.cpu_percent(interval=0.0)
                    mem_info = proc.memory_info()
                    ram_usage_mb = round(mem_info.rss / (1024 * 1024), 2)
                    
                    proc_uptime_sec = current_time - proc.create_time()
                    uptime_str = format_uptime(proc_uptime_sec)
                except:
                    pass
                
                if proc_name == 'docker-proxy':
                    container_name = get_docker_container_by_port(port)
                    if container_name:
                        cmd_str = f"Docker Container: {container_name}"

                elif cwd and proc_name in ['python3', 'python', 'gunicorn']:
                    cmd_str = f"{cmd_str}  (Dir: {cwd})"
                    
            except psutil.AccessDenied:
                proc_name = "ACCESS DENIED"
                cmd_str = "⚠️ ต้องรัน Web App นี้ด้วยสิทธิ์ sudo (root)"
            except psutil.NoSuchProcess:
                proc_name = "UNKNOWN"
                cmd_str = "Process สิ้นสุดการทำงาน"

            ports_list.append({
                "port": port,
                "ip": ip,
                "pid": pid,
                "process": proc_name,
                "command": cmd_str,
                "service_name": service_name,
                "container_name": container_name,
                "cpu": cpu_usage,
                "ram": ram_usage_mb,
                "uptime": uptime_str
            })
    except Exception as e:
        print(f"[Error] in get_ports_data: {e}")
        
    return ports_list

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == DEFAULT_PASSWORD:
            session.permanent = True 
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่")

    if not session.get('authenticated'):
        return render_template('login.html', error=None)

    data = get_ports_data()
    return render_template('index.html', ports=data)

@app.route('/system_stats', methods=['GET'])
def system_stats():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = round(mem.used / (1024**3), 2)
        ram_total_gb = round(mem.total / (1024**3), 2)
        
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = round(disk.used / (1024**3), 2)
        disk_total_gb = round(disk.total / (1024**3), 2)
        
        server_uptime_sec = time.time() - psutil.boot_time()
        server_uptime_str = format_uptime(server_uptime_sec)
        
        return jsonify({
            "status": "success",
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "disk_percent": disk_percent,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "server_uptime": server_uptime_str
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/action', methods=['POST'])
def perform_action():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    action = request.form.get('action')
    target_type = request.form.get('type')     
    target_val = request.form.get('target')    

    try:
        if target_type == 'docker':
            if action in ['stop', 'restart', 'kill']:
                subprocess.run(['docker', action, target_val], check=True)
                return jsonify({"status": "success", "message": f"สั่ง {action.capitalize()} Docker Container '{target_val}' เรียบร้อยแล้ว"})
        
        elif target_type == 'service':
            if action in ['stop', 'restart']:
                subprocess.run(['systemctl', action, target_val], check=True)
                return jsonify({"status": "success", "message": f"สั่ง {action.capitalize()} Service '{target_val}' เรียบร้อยแล้ว"})
        
        elif target_type == 'process':
            if action == 'kill' and target_val.isdigit():
                os.kill(int(target_val), signal.SIGKILL)
                return jsonify({"status": "success", "message": f"Kill Process PID: {target_val} เรียบร้อยแล้ว"})

        return jsonify({"status": "error", "message": "คำสั่งไม่ถูกต้อง"})

    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"Execution Error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/service_info', methods=['POST'])
def service_info():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    service_name = request.form.get('service_name')
    if not service_name:
        return jsonify({"status": "error", "message": "ไม่พบชื่อ Service"}), 400

    try:
        result = subprocess.run(['systemctl', 'show', '-p', 'FragmentPath', service_name], capture_output=True, text=True)
        path_match = re.search(r'FragmentPath=(.+)', result.stdout)
        
        if path_match and path_match.group(1).strip():
            filepath = path_match.group(1).strip()
            
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = f.read()
                return jsonify({"status": "success", "filepath": filepath, "content": content})
            else:
                return jsonify({"status": "error", "message": f"ไม่พบไฟล์ Service ที่: {filepath}"})
        
        return jsonify({"status": "error", "message": "ไม่สามารถระบุตำแหน่งไฟล์ Service นี้ได้"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/save_service', methods=['POST'])
def save_service():
    """API สำหรับบันทึกไฟล์ (สร้างใหม่/แก้ไข) Service และรีโหลด Daemon"""
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    service_name = request.form.get('service_name')
    content = request.form.get('content')
    is_new = request.form.get('is_new') == 'true'

    if not service_name or not content:
        return jsonify({"status": "error", "message": "ข้อมูลไม่ครบถ้วน กรุณากรอกชื่อและเนื้อหา"}), 400

    if not service_name.endswith('.service'):
        service_name += '.service'

    try:
        # กำหนด Path เริ่มต้นสำหรับการสร้างใหม่
        filepath = f"/etc/systemd/system/{service_name}"
        
        # กรณีเป็นการแก้ไข ให้ดึง Path ปัจจุบันก่อนเผื่อไฟล์อยู่ตำแหน่งอื่น (เช่น /lib/systemd/system)
        if not is_new:
            result = subprocess.run(['systemctl', 'show', '-p', 'FragmentPath', service_name], capture_output=True, text=True)
            path_match = re.search(r'FragmentPath=(.+)', result.stdout)
            if path_match and path_match.group(1).strip():
                filepath = path_match.group(1).strip()

        # เขียนไฟล์
        with open(filepath, 'w') as f:
            f.write(content)
            
        # กำหนดสิทธิ์ให้ปลอดภัย
        os.chmod(filepath, 0o644)
        
        # โหลดค่า systemctl ใหม่
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        
        return jsonify({
            "status": "success", 
            "message": f"บันทึกไฟล์และ Reload Daemon สำเร็จ\n({filepath})"
        })

    except PermissionError:
        return jsonify({"status": "error", "message": "Permission Denied: การแก้ไข/สร้าง Service ต้องใช้สิทธิ์ sudo (root)"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/view_log', methods=['POST'])
def view_log():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    target_type = request.form.get('type')
    target_val = request.form.get('target')

    if not target_val:
        return jsonify({"status": "error", "message": "ไม่พบเป้าหมาย"}), 400

    try:
        log_content = ""
        if target_type == 'docker':
            result = subprocess.run(['docker', 'logs', '--tail', '100', target_val], capture_output=True, text=True, stderr=subprocess.STDOUT)
            log_content = result.stdout
        elif target_type == 'service':
            result = subprocess.run(['journalctl', '-u', target_val, '-n', '100', '--no-pager'], capture_output=True, text=True)
            log_content = result.stdout
        else:
            return jsonify({"status": "error", "message": "ประเภทไม่ถูกต้อง"})

        if not log_content.strip():
            log_content = "ไม่มีข้อมูล Log (Empty Log)"

        return jsonify({"status": "success", "log": log_content, "target": target_val})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    if os.name == 'posix' and os.geteuid() != 0:
        print("\n" + "="*60)
        print("⚠️  WARNING: คุณไม่ได้รันสคริปต์นี้ด้วยสิทธิ์ root (sudo)")
        print("แอปจะรันได้ปกติ แต่คุณอาจจะไม่สามารถ สร้าง/แก้ไข Service ได้")
        print("คำแนะนำ: กด Ctrl+C แล้วรันใหม่ด้วยคำสั่ง 'sudo python3 app.py'")
        print("="*60 + "\n")
        
    # หากรันไม่ได้รหัสผ่าน .env ระบบจะเตือนใน Console
    if not os.environ.get('DASHBOARD_PASS'):
        print("[INFO] ไม่พบไฟล์ .env ระบบจะใช้รหัสผ่านชั่วคราว: admin1234")

    app.run(host='0.0.0.0', port=PORT, debug=DEBUG_APP)
