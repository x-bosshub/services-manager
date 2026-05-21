นี่คือเอกสารสรุปรายละเอียดของระบบ **BossHub Server Monitor** ที่เราเพิ่งพัฒนาร่วมกันครับ เพื่อให้คุณใช้เป็น Reference ในการนำไปใช้งานจริง หรืออธิบายให้ทีมงานฟังได้อย่างชัดเจนครับ
## 1. การทำงานของระบบ (System Architecture & Workflow)
ระบบนี้ถูกออกแบบมาในลักษณะ **Agent-based Dashboard** โดยให้แอปพลิเคชัน Python (Flask) ทำหน้าที่เป็นตัวกลาง (Middleware) ระหว่างผู้ใช้งานกับระบบปฏิบัติการ Linux ทำงานประสานกัน 2 ส่วนหลัก:
 * **ฝั่ง Backend (OS Controller):**
   * **OS Interface:** ใช้ไลบรารี psutil เจาะเข้าไปอ่านข้อมูลระดับ OS ดึงรายการ Network Connections ที่อยู่ในสถานะ LISTEN (กำลังรอรับ Request) และจับคู่กับ Process ID (PID)
   * **Resource Profiling:** คำนวณการใช้ CPU (%) และ RAM (MB) รวมถึง Uptime ของแต่ละโปรเซสแบบ Real-time
   * **Command Execution:** ใช้ subprocess.run() ในการยิงคำสั่ง Linux ปกติ (เช่น systemctl, docker, journalctl) โดยตรง ซึ่งเร็วกว่าและเสถียรกว่าการเขียน Shell Script ซับซ้อน
 * **ฝั่ง Frontend (Interactive UI):**
   * หน้าเว็บเขียนด้วย HTML/JS แบบ Single-page feel ใช้เทคนิค AJAX (fetch API) วิ่งไปขอข้อมูลภาพรวม (CPU, RAM, Disk) ทุกๆ 3 วินาทีเพื่ออัปเดต Dashboard
   * มีการใช้ DOM Manipulation เพื่อเช็กค่า CPU/RAM ฝั่ง Client และไฮไลต์แถวที่กินทรัพยากรสูงสุดโดยอัตโนมัติ
## 2. ขอบเขตของระบบ (System Scope)
ระบบนี้ถูกจำกัดและออกแบบมาให้ทำหน้าที่เฉพาะส่วนที่เกี่ยวข้องกับการ "บริการเครือข่าย" (Network Services) เป็นหลัก เพื่อไม่ให้ข้อมูลล้นหน้าจอเกินไป
**✅ สิ่งที่ระบบ "ทำได้" (In Scope):**
 * **Monitor Service:** ตรวจจับเฉพาะโปรเซสที่มีการเปิด Port ไว้เท่านั้น (Web Server, Database, Custom API, Docker Container)
 * **Systemd Management:** สร้างไฟล์ Service ใหม่, เปิดอ่านโค้ด Service, แก้ไขโค้ดและ daemon-reload อัตโนมัติ, ดู Log 100 บรรทัดล่าสุด, สั่ง Start/Stop/Restart
 * **Docker Management:** ตรวจจับ Container ที่ผูก Port ออกมาด้านนอก, สั่ง Stop/Restart/Kill, และดู Docker Logs
 * **Process Management:** บังคับปิด (Kill) โปรเซสทั่วไปที่ไม่ได้ผูกกับ Service หรือ Docker ได้โดยตรงผ่านระดับ OS (SIGKILL)
**❌ สิ่งที่ระบบ "ทำไม่ได้" (Out of Scope):**
 * **Background Tasks ที่ไม่เปิด Port:** สคริปต์ที่รันวนลูปทำงานเงียบๆ เบื้องหลัง (เช่น Cronjobs หรือ AI Inference script ที่ไม่ได้รันเป็น Web API) จะไม่แสดงในตารางนี้ ยกเว้นจะถูกตั้งเป็น Systemd Service
 * **การจัดการ Firewall (UFW/Iptables):** ไม่สามารถเปิด-ปิด Port ที่ระดับ Firewall ผ่านหน้าเว็บได้
 * **Real-time Log Streaming:** Log จะดึงมาแสดงผลครั้งละ 100 บรรทัดล่าสุด ไม่ใช่การ tail -f ที่ไหลแบบ Real-time (เพื่อประหยัดทรัพยากรเบราว์เซอร์)
## 3. ความปลอดภัย (Security & Mitigations)
เนื่องจากระบบนี้ **"จำเป็นต้องรันด้วยสิทธิ์ root (sudo)"** การออกแบบความปลอดภัยจึงเป็นเรื่องสำคัญที่สุด ซึ่งเราได้วางกลไกป้องกันไว้ดังนี้:
**ระดับ Application (ที่เราเขียนไปแล้ว):**
 1. **Session & Secret Key:** ใช้ไลบรารี secrets สร้าง Key แบบ Cryptographically Secure บันทึกลงไฟล์ ป้องกันไม่ให้ Key เปลี่ยนเมื่อ Service รีสตาร์ท (แก้ปัญหา Session หลุด)
 2. **Session Expiry:** บังคับให้ Session มีอายุแค่ 60 นาที (Time-out) ป้องกันการล็อกอินค้างไว้บนเครื่องส่วนกลาง
 3. **Command Injection Prevention:** การเรียก subprocess.run() เราส่งค่าในรูปแบบ Array List (เช่น ['docker', 'stop', target]) แทนการใช้ shell=True ทำให้ผู้ไม่หวังดีไม่สามารถแฮกด้วยการส่ง string แบบ target="container_name; rm -rf /" เข้ามาได้
 4. **Safe-Guard Port 22:** โค้ดมีการดัก Exception if port == 22: continue ไว้เสมอ ป้องกันไม่ให้แอดมินเผลอกด Kill Process ของ SSH จนตัวเองหลุดออกจากเซิร์ฟเวอร์
 5. **Secure File Write:** เมื่อสร้างหรือแก้ไฟล์ Service โค้ดจะบังคับตั้งสิทธิ์ os.chmod(filepath, 0o644) เสมอ
**ข้อควรระวังและแนวทางสำหรับ Production (สิ่งที่ต้องทำเพิ่มฝั่ง Infra):**
 * **ห้าม Expose Port นี้ออกสู่ Public Internet โดยตรง:** แม้จะมีหน้า Login ดักไว้ แต่การส่งรหัสผ่านผ่าน HTTP ธรรมดาสามารถถูกดักจับ (Sniffing) ได้
   * *ทางแก้:* ควรเอา Dashboard นี้ไปซ่อนไว้หลัง **Reverse Proxy (Nginx หรือ Cloudflare Tunnel / ngrok)** และบังคับให้ใช้งานผ่าน **HTTPS** เท่านั้น
 * **Hardcoded Password:** ปัจจุบันรหัสผ่านคือ DEFAULT_PASSWORD = "password"
   * *ทางแก้:* ก่อนนำขึ้นเซิร์ฟเวอร์จริง ควรเปลี่ยนรหัสผ่านนี้ให้คาดเดายาก หรือเปลี่ยนไปดึงจาก Environment Variables (os.environ.get('DASHBOARD_PASS')) เพื่อไม่ให้รหัสผ่านหลุดไปอยู่ใน Source Code ครับ


# ติดตั้งครั้งแรก
```
sudo apt update
sudo apt install python3-pip
sudo pip3 install flask psutil
```
# รันโปรแกรม (แบบ Manual เพื่อทดสอบ)
```
sudo python3 app.py
```
# ทำให้ระบบรันเองตลอดเวลา (ตั้งเป็น Systemd Service)
​เพื่อให้หน้า Dashboard นี้เป็น "ตัวคุมเซิร์ฟเวอร์" มันจึงไม่ควรตายเมื่อเราปิด Terminal ครับ เราจะสร้าง Service ให้มันทำงานอยู่เบื้องหลังเสมอ
​1. สร้างไฟล์ Service ใหม่: 

```
sudo nano /etc/systemd/system/bosshub-monitor.service
```

2. ใส่โค้ดนี้ลงไป (เปลี่ยน WorkingDirectory ให้ตรงกับ Path ):

```
[Unit]
Description=BossHub Server Port Monitor
After=network.target

[Service]
User=root
WorkingDirectory=/root/services-manager
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. บันทึกไฟล์ (Ctrl+O -> Enter -> Ctrl+X) และสั่ง Start Service:
```
sudo systemctl daemon-reload
sudo systemctl enable aibosshub-monitor
sudo systemctl start aibosshub-monitor
```
เพียงเท่านี้ ระบบ Dashboard ของคุณ
