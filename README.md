# AI Face Tracking with Gesture Photo Capture

โปรเจกต์นี้เป็นการใช้ Python ร่วมกับ OpenCV และ MediaPipe ในการตรวจจับและติดตามใบหน้า (Face Tracking) พร้อมกับควบคุมการเคลื่อนไหวของเซอร์โวมอเตอร์ผ่านบอร์ด Arduino นอกจากนี้ยังเพิ่มฟีเจอร์การยกมือเพื่อสั่งถ่ายภาพได้อีกด้วย[cite: 1]

## ฟีเจอร์หลัก (Key Features)
*   **Face Tracking**: ตรวจจับใบหน้าและส่งคำสั่งควบคุมเซอร์โวมอเตอร์ผ่าน Arduino[cite: 1]
*   **Smooth Movement**: มีการตั้งค่าการเคลื่อนที่ของเซอร์โวและการจับภาพให้มีความสมูท (Smoothing) ลดการกระตุก[cite: 1]
*   **Gesture Photo Capture**: ตรวจจับการยกมือ (ชู 3 นิ้วขึ้นไป) เพื่อสั่งถ่ายภาพอัตโนมัติพร้อมนับถอยหลัง[cite: 1]

## สิ่งที่ต้องใช้ (Prerequisites)
**Software:**
*   Python 3.x
*   OpenCV (`pip install opencv-python`)[cite: 1]
*   MediaPipe (`pip install mediapipe`)[cite: 1]
*   PySerial (`pip install pyserial`)[cite: 1]

**Hardware:**
*   กล้อง Webcam (รองรับการใช้งานผ่าน Iriun Webcam)[cite: 1]
*   บอร์ด Arduino (สำหรับการรับคำสั่งหมุนเซอร์โว)[cite: 1]
*   เซอร์โวมอเตอร์[cite: 1]

## วิธีการใช้งาน (How to use)
1.  **เชื่อมต่อ Arduino**: ตรวจสอบว่า Arduino เชื่อมต่ออยู่ที่พอร์ตไหน และตั้งค่าในไฟล์ `face_tracking.py` (ค่าเริ่มต้นคือ `COM9` Baud rate `9600`)[cite: 1]
2.  **ตั้งค่ากล้อง**: ตรวจสอบหมายเลขกล้องที่ใช้งาน (ค่าเริ่มต้นคือ `CAMERA_ID = 1`)[cite: 1]
3.  **รันโปรแกรม**:
    ```bash
    python face_tracking.py
    ```
4.  กล้องจะเปิดขึ้นมา หากตรวจพบใบหน้าจะเริ่มทำการติดตาม[cite: 1]
5.  หากต้องการถ่ายภาพ ให้ยกมือขึ้น (เหยียดนิ้วอย่างน้อย 3 นิ้ว) ระบบจะเริ่มนับถอยหลัง 3 วินาทีแล้วทำการบันทึกภาพลงในโฟลเดอร์ `captured_photos`[cite: 1]
6.  กดปุ่ม `q` เพื่อออกจากโปรแกรม[cite: 1]
