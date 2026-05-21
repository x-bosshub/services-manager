# services-manager
ระบบจัดการ services

# ติดตั้งครั้งแรก
sudo apt update
sudo apt install python3-pip
sudo pip3 install flask psutil

# รันโปรแกรม (แบบ Manual เพื่อทดสอบ)
sudo python3 app.py

# ทำให้ระบบรันเองตลอดเวลา (ตั้งเป็น Systemd Service)
​เพื่อให้หน้า Dashboard นี้เป็น "ตัวคุมเซิร์ฟเวอร์" มันจึงไม่ควรตายเมื่อเราปิด Terminal ครับ เราจะสร้าง Service ให้มันทำงานอยู่เบื้องหลังเสมอ
​1. สร้างไฟล์ Service ใหม่: 
    `sudo nano /etc/systemd/system/bosshub-monitor.service`

2. ใส่โค้ดนี้ลงไป (เปลี่ยน WorkingDirectory ให้ตรงกับ Path ):
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


3. บันทึกไฟล์ (Ctrl+O -> Enter -> Ctrl+X) และสั่ง Start Service:
   sudo systemctl daemon-reload
sudo systemctl enable aibosshub-monitor
sudo systemctl start aibosshub-monitor

เพียงเท่านี้ ระบบ Dashboard ของคุณ
