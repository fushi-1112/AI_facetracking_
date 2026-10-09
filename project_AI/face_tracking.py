import cv2
import math
import serial
import time
import os
import mediapipe as mp
from datetime import datetime

# ==========================================
# CAMERA & ARDUINO SETTINGS
# ==========================================
CAMERA_ID = 1
ARDUINO_PORT = "COM9"
BAUD_RATE = 9600

# ==========================================
# SERVO TRACKING SETTINGS
# ==========================================
SERVO_STOP = 90
SERVO_MIN_SPEED = 3
SERVO_MAX_SPEED = 7
COMMAND_REFRESH_INTERVAL = 0.1
FACE_POSITION_SMOOTHING = 0.6   # สูง = ตอบสนองเร็ว หน่วงน้อย (ลดการหมุนเลย)
BOX_SMOOTHING = 0.5          # smooth กรอบหน้า (ยิ่งน้อยยิ่งนิ่ง)

REVERSE_SERVO = True
CENTER_ZONE = 140            # หน้าเข้าโซนนี้ -> สั่งหยุด
TRACK_RESTART_MARGIN = 120   # ต้องออกจากโซนไปไกลกว่านี้อีก จึงเริ่มหมุนใหม่ (dead band)
GAIN = 0.015

STOP_LEAD = 60               # สั่งหยุดก่อนถึงโซนกลางอีกกี่ px (ชดเชยการหมุนเลย)
SLOW_DISTANCE = 200          # ใกล้โซนกลางในระยะนี้ -> ใช้ความเร็วต่ำสุด

SETTLE_TIME = 0.8            # วินาทีที่รอหลังหยุด ให้ภาพ/กล้องนิ่งก่อนตัดสินใจใหม่
RESTART_CONFIRM_FRAMES = 5   # หน้าต้องอยู่นอกโซนติดกันกี่เฟรมก่อนเริ่มหมุน

# ==========================================
# FACE DETECTION SETTINGS
# ==========================================
FACE_MIN_SIZE = 60            # px ขนาดหน้าเล็กสุดที่ยอมรับ
FACE_MIN_CONFIDENCE = 0.6
FACE_CONFIRM_FRAMES = 2       # ต้องเจอติดกันกี่เฟรมก่อนล็อกเป้า
MAX_MISSED_FRAMES = 15        # หน้าหายกี่เฟรมจึงเลิกล็อกเป้า
HOLD_FRAMES = 4               # หน้าหายชั่วคราว ให้ servo ใช้ตำแหน่งเดิมไปก่อน

# ==========================================
# HAND PHOTO SETTINGS
# ==========================================
PHOTO_COUNTDOWN = 3.0
PHOTO_FOLDER = "captured_photos"

os.makedirs(PHOTO_FOLDER, exist_ok=True)

# ==========================================
# MEDIAPIPE
# ==========================================
mpHands = mp.solutions.hands
mpDraw = mp.solutions.drawing_utils
mpFace = mp.solutions.face_detection

handsDetector = mpHands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)

faceDetector = mpFace.FaceDetection(
    model_selection=1,   # 1 = ระยะไกล (~5 ม.), 0 = ระยะใกล้ (~2 ม.)
    min_detection_confidence=FACE_MIN_CONFIDENCE
)

# ==========================================
# OPEN CAMERA
# ==========================================
videoCam = cv2.VideoCapture(CAMERA_ID, cv2.CAP_MSMF)

if not videoCam.isOpened():
    print("ไม่สามารถเปิด Iriun Webcam ได้")
    handsDetector.close()
    faceDetector.close()
    raise SystemExit

videoCam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
videoCam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
videoCam.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def detect_faces(rgb_frame, frame_w, frame_h):
    """คืนลิสต์ของ (x, y, w, h) หน้าที่ตรวจเจอ"""
    results = faceDetector.process(rgb_frame)
    faces = []

    if not results.detections:
        return faces

    for det in results.detections:
        box = det.location_data.relative_bounding_box

        x = max(0, int(box.xmin * frame_w))
        y = max(0, int(box.ymin * frame_h))
        w = min(int(box.width * frame_w), frame_w - x)
        h = min(int(box.height * frame_h), frame_h - y)

        if w >= FACE_MIN_SIZE and h >= FACE_MIN_SIZE:
            faces.append((x, y, w, h))

    return faces


def is_hand_raised(landmarks):
    """ตรวจว่ามีนิ้วชี้ กลาง นาง และก้อยเหยียดขึ้นอย่างน้อย 3 นิ้วหรือไม่"""
    lm = landmarks.landmark

    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]

    fingers_up = sum(
        1
        for tip, pip in zip(finger_tips, finger_pips)
        if lm[tip].y < lm[pip].y
    )

    return fingers_up >= 3


# ==========================================
# CONNECT ARDUINO
# ==========================================
try:
    arduino = serial.Serial(
        ARDUINO_PORT,
        BAUD_RATE,
        timeout=1
    )

    time.sleep(2)
    arduino.write(f"ANGLE:{SERVO_STOP}\n".encode())

except Exception as e:
    print("ไม่สามารถเชื่อมต่อ Arduino:", e)
    videoCam.release()
    handsDetector.close()
    faceDetector.close()
    raise SystemExit


# ==========================================
# INITIAL STATES
# ==========================================
lastServoCommand = SERVO_STOP
lastCommandTime = time.monotonic()

isTracking = False
settleUntil = 0.0
restartFrames = 0
targetFace = None            # กรอบที่ smooth แล้ว (int)
smoothedBox = None           # กรอบที่ smooth แล้ว (float)
smoothedFaceCenterX = None
missedFrames = 0

pendingFace = None
pendingFaceFrames = 0

photoCountdownStarted = None
photoTakenForGesture = False


def smooth_box(new_box):
    global smoothedBox
    if smoothedBox is None:
        smoothedBox = [float(v) for v in new_box]
    else:
        smoothedBox = [
            (1 - BOX_SMOOTHING) * old + BOX_SMOOTHING * new
            for old, new in zip(smoothedBox, new_box)
        ]
    return tuple(int(v) for v in smoothedBox)


try:
    while True:
        ret, frame = videoCam.read()

        if not ret:
            print("อ่านภาพจาก Iriun ไม่ได้")
            break

        frame = cv2.flip(frame, 1)

        # ภาพสะอาด ใช้ทั้งถ่ายรูปและ detect (ยังไม่มีอะไรวาดทับ)
        photoFrame = frame.copy()

        height, width = frame.shape[:2]
        centerX = width // 2

        rgbFrame = cv2.cvtColor(photoFrame, cv2.COLOR_BGR2RGB)
        rgbFrame.flags.writeable = False

        # ==========================================
        # HAND DETECTION
        # ==========================================
        handResults = handsDetector.process(rgbFrame)
        handRaised = False

        # ==========================================
        # FACE DETECTION (ใช้ภาพสะอาด)
        # ==========================================
        faceCandidates = detect_faces(rgbFrame, width, height)

        # ค่อยวาดทีหลัง detect เสร็จ
        if handResults.multi_hand_landmarks:
            handLandmarks = handResults.multi_hand_landmarks[0]
            handRaised = is_hand_raised(handLandmarks)

            mpDraw.draw_landmarks(
                frame,
                handLandmarks,
                mpHands.HAND_CONNECTIONS
            )

        zoneLeft = centerX - CENTER_ZONE
        zoneRight = centerX + CENTER_ZONE

        cv2.rectangle(frame, (zoneLeft, 0), (zoneRight, height), (255, 255, 0), 2)
        cv2.line(frame, (centerX, 0), (centerX, height), (255, 0, 255), 2)

        selectedFace = None

        # ==========================================
        # KEEP TRACKING THE SAME FACE
        # ==========================================
        if targetFace is not None:
            oldX, oldY, oldW, oldH = targetFace

            oldCenterX = oldX + oldW // 2
            oldCenterY = oldY + oldH // 2

            matches = []

            for candidate in faceCandidates:
                x, y, w, h = candidate

                candidateCenterX = x + w // 2
                candidateCenterY = y + h // 2

                centerDistance = (
                    (candidateCenterX - oldCenterX) ** 2
                    + (candidateCenterY - oldCenterY) ** 2
                ) ** 0.5

                sizeRatio = (w * h) / max(1, oldW * oldH)

                if (
                    centerDistance <= max(120, oldW * 1.8)
                    and 0.4 <= sizeRatio <= 2.5
                ):
                    matches.append((centerDistance, candidate))

            if matches:
                bestMatch = min(matches, key=lambda item: item[0])[1]

                selectedFace = smooth_box(bestMatch)
                targetFace = selectedFace
                missedFrames = 0

            else:
                missedFrames += 1

                if missedFrames > MAX_MISSED_FRAMES:
                    targetFace = None
                    smoothedBox = None
                    smoothedFaceCenterX = None
                    isTracking = False
                    pendingFace = None
                    pendingFaceFrames = 0

        elif faceCandidates:
            candidate = max(
                faceCandidates,
                key=lambda face: face[2] * face[3]
            )

            if pendingFace is not None:
                oldX, oldY, oldW, oldH = pendingFace
                x, y, w, h = candidate

                oldCenterX = oldX + oldW // 2
                oldCenterY = oldY + oldH // 2

                candidateCenterX = x + w // 2
                candidateCenterY = y + h // 2

                centerDistance = (
                    (candidateCenterX - oldCenterX) ** 2
                    + (candidateCenterY - oldCenterY) ** 2
                ) ** 0.5

                sizeRatio = (w * h) / max(1, oldW * oldH)

                if (
                    centerDistance <= max(80, oldW)
                    and 0.6 <= sizeRatio <= 1.7
                ):
                    pendingFaceFrames += 1
                else:
                    pendingFaceFrames = 1

            else:
                pendingFaceFrames = 1

            pendingFace = candidate

            if pendingFaceFrames >= FACE_CONFIRM_FRAMES:
                smoothedBox = None
                selectedFace = smooth_box(candidate)
                targetFace = selectedFace
                smoothedFaceCenterX = None
                missedFrames = 0
                pendingFace = None
                pendingFaceFrames = 0

        else:
            pendingFace = None
            pendingFaceFrames = 0

        # หน้าหายชั่วคราว: ใช้ตำแหน่งเดิมไปก่อน ไม่ให้ servo กระตุก
        heldFace = None
        if (
            selectedFace is None
            and targetFace is not None
            and missedFrames <= HOLD_FRAMES
        ):
            heldFace = targetFace

        activeFace = selectedFace if selectedFace is not None else heldFace

        # ==========================================
        # SERVO CONTROL
        # ==========================================
        if activeFace is not None:
            x, y, w, h = activeFace

            faceCenterX = x + w // 2
            faceCenterY = y + h // 2

            boxColor = (0, 255, 0) if selectedFace is not None else (0, 255, 255)

            cv2.rectangle(frame, (x, y), (x + w, y + h), boxColor, 3)
            cv2.circle(frame, (faceCenterX, faceCenterY), 8, (0, 0, 255), -1)

            # อัปเดตตำแหน่งเฉพาะเมื่อเจอหน้าจริง
            if selectedFace is not None:
                if smoothedFaceCenterX is None:
                    smoothedFaceCenterX = float(faceCenterX)
                else:
                    smoothedFaceCenterX = (
                        (1 - FACE_POSITION_SMOOTHING) * smoothedFaceCenterX
                        + FACE_POSITION_SMOOTHING * faceCenterX
                    )

            errorX = round(smoothedFaceCenterX - centerX)

            currentTime = time.monotonic()

            faceInsideCenterZone = abs(errorX) <= CENTER_ZONE + STOP_LEAD
            faceOutsideRestartZone = (
                abs(errorX) >= CENTER_ZONE + TRACK_RESTART_MARGIN
            )

            if isTracking:
                if faceInsideCenterZone:
                    isTracking = False
                    settleUntil = currentTime + SETTLE_TIME
                    restartFrames = 0
            elif (
                faceOutsideRestartZone
                and currentTime >= settleUntil
                and selectedFace is not None
            ):
                restartFrames += 1

                if restartFrames >= RESTART_CONFIRM_FRAMES:
                    isTracking = True
                    restartFrames = 0
            else:
                restartFrames = 0

            servoCommand = SERVO_STOP
            status = "CENTER"

            if isTracking:
                status = "MOVING"

                distance = abs(errorX) - CENTER_ZONE

                if distance < SLOW_DISTANCE:
                    speed = SERVO_MIN_SPEED
                else:
                    speed = min(
                        SERVO_MAX_SPEED,
                        SERVO_MIN_SPEED + int(distance * GAIN)
                    )

                direction = 1 if errorX > 0 else -1

                if REVERSE_SERVO:
                    direction = -direction

                servoCommand = SERVO_STOP + direction * speed

            if heldFace is not None:
                status += " (HOLD)"

            if (
                servoCommand != lastServoCommand
                or currentTime - lastCommandTime >= COMMAND_REFRESH_INTERVAL
            ):
                arduino.write(f"ANGLE:{servoCommand}\n".encode())

                lastServoCommand = servoCommand
                lastCommandTime = currentTime

            cv2.putText(frame, status, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.putText(frame, f"Face X: {faceCenterX}", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            cv2.putText(frame, f"Error: {errorX}", (20, 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            cv2.putText(frame, f"Servo command: {servoCommand}", (20, 135),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        else:
            currentTime = time.monotonic()

            if (
                lastServoCommand != SERVO_STOP
                or currentTime - lastCommandTime >= COMMAND_REFRESH_INTERVAL
            ):
                arduino.write(f"ANGLE:{SERVO_STOP}\n".encode())

                lastServoCommand = SERVO_STOP
                lastCommandTime = currentTime

            status = "VERIFYING FACE" if pendingFace is not None else "NO FACE"

            cv2.putText(frame, status, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

        # ==========================================
        # RAISE HAND TO TAKE PHOTO
        # ==========================================
        now = time.monotonic()

        if handRaised:
            if not photoTakenForGesture and photoCountdownStarted is None:
                photoCountdownStarted = now

            if photoCountdownStarted is not None and not photoTakenForGesture:
                elapsed = now - photoCountdownStarted
                remaining = PHOTO_COUNTDOWN - elapsed

                if remaining > 0:
                    displayNumber = math.ceil(remaining)

                    cv2.putText(frame, f"PHOTO IN {displayNumber}", (20, 185),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)

                else:
                    filename = datetime.now().strftime("photo_%Y%m%d_%H%M%S_%f.jpg")
                    filepath = os.path.join(PHOTO_FOLDER, filename)

                    saved = cv2.imwrite(filepath, photoFrame)

                    if saved:
                        print(f"ถ่ายภาพสำเร็จ: {filepath}")
                        photoTakenForGesture = True

                        cv2.putText(frame, "PHOTO SAVED!", (20, 185),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
                    else:
                        print("บันทึกภาพไม่สำเร็จ")
                        photoCountdownStarted = None
        else:
            photoCountdownStarted = None
            photoTakenForGesture = False

        handStatus = (
            "HAND UP: PHOTO"
            if handRaised
            else "Raise your hand to take a photo"
        )

        cv2.putText(
            frame, handStatus, (20, 225),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
            (0, 255, 0) if handRaised else (255, 255, 255), 2
        )

        cv2.imshow("Face Tracking + Gesture Photo", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    try:
        arduino.write(f"ANGLE:{SERVO_STOP}\n".encode())
        time.sleep(0.1)
    except Exception:
        pass

    videoCam.release()

    try:
        arduino.close()
    except Exception:
        pass

    handsDetector.close()
    faceDetector.close()
    cv2.destroyAllWindows()

    print("Program stopped.")