# -*- coding: utf-8 -*-
import cv2
import mediapipe as mp
import numpy as np
# import requests # Không cần nữa nếu chỉ dùng MQTT
import math
import time
import threading
from queue import Queue, Empty
from scipy.ndimage import gaussian_filter1d
import uuid
from typing import List, Tuple, Optional
import paho.mqtt.client as mqtt # <<<--- Thêm thư viện MQTT

# --- MediaPipe Initialization ---
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(model_complexity=0, max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)

# --- MQTT Configuration ---
MQTT_BROKER = "localhost"  # Địa chỉ IP hoặc hostname của MQTT broker (ví dụ: Mosquitto)
MQTT_PORT = 1883           # Port MQTT mặc định
MQTT_TOPIC = "car/command" # Topic để publish lệnh điều khiển
MQTT_CLIENT_ID = f"gesture_controller_{uuid.uuid4()}" # Tạo ID client duy nhất

# --- HTTP Configuration (Giữ lại nếu bạn muốn dùng song song, nếu không thì xóa) ---
# SERVER_URL = "http://localhost:8000/control"

# --- Constants ---
MAX_POINTS = 65
MIN_POINTS_CIRCLE = 10
MIN_POINTS_RECTANGLE = 12
MIN_POINTS_TRIANGLE = 15
COMMAND_COOLDOWN = 0.5
MIN_RADIUS = 20
MIN_SIDE_LENGTH = 20
MIN_AREA = 500
STARTUP_DURATION = 1.5
CLOSURE_THRESHOLD = 30
MIN_POINT_DISTANCE = 5
HAND_DETECTION_DRAW_DELAY = 0.75
NO_HAND_TIMEOUT = 1.0

# --- Globals ---
command_queue = Queue(maxsize=10)
points: List[Tuple[int, int]] = []
mqtt_connected = False # <<<--- Biến trạng thái kết nối MQTT

# --- Utility Functions (Giữ nguyên) ---
def smooth_points(pts: List[Tuple[int, int]], sigma: float = 1.5) -> List[Tuple[int, int]]:
    try:
        if len(pts) < 2: return pts
        np_pts = np.array(pts, dtype=np.float32)
        smoothed_x = gaussian_filter1d(np_pts[:, 0], sigma=sigma, mode='nearest')
        smoothed_y = gaussian_filter1d(np_pts[:, 1], sigma=sigma, mode='nearest')
        return [(int(x), int(y)) for x, y in zip(smoothed_x, smoothed_y)]
    except Exception as e: print(f"Error smooth: {e}"); return pts

def calculate_angle(p1: Tuple[int, int], p2: Tuple[int, int], p3: Tuple[int, int]) -> float:
    try:
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        norm_v1 = np.linalg.norm(v1); norm_v2 = np.linalg.norm(v2)
        if norm_v1 < 1e-6 or norm_v2 < 1e-6: return 0.0
        dot_product = np.dot(v1, v2)
        cos_theta = np.clip(dot_product / (norm_v1 * norm_v2), -1.0, 1.0)
        return math.degrees(math.acos(cos_theta))
    except Exception as e: print(f"Error angle: {e}"); return 0.0

def calculate_area(pts: List[Tuple[int, int]]) -> float:
    try:
        if len(pts) < 3: return 0.0
        area = 0.0; n = len(pts)
        for i in range(n): j = (i + 1) % n; area += pts[i][0] * pts[j][1]; area -= pts[j][0] * pts[i][1]
        return abs(area) / 2.0
    except Exception as e: print(f"Error area: {e}"); return 0.0

def is_closed_shape(pts: List[Tuple[int, int]], threshold: float = CLOSURE_THRESHOLD) -> bool:
    try:
        if len(pts) < 3: return False
        return math.dist(pts[0], pts[-1]) < threshold
    except Exception as e: print(f"Error closed: {e}"); return False

def is_circle(pts: List[Tuple[int, int]], tolerance: float = 0.28) -> bool:
    try:
        if len(pts) < MIN_POINTS_CIRCLE or not is_closed_shape(pts): return False
        np_pts = np.array(pts, dtype=np.float32)
        (cx, cy), radius = cv2.minEnclosingCircle(np_pts)
        center = (float(cx), float(cy))
        if radius < MIN_RADIUS: return False
        area = calculate_area(pts)
        if area < MIN_AREA: return False
        theoretical_area = math.pi * radius * radius
        if theoretical_area < 1e-6: return False
        area_ratio = area / theoretical_area
        if not (0.55 < area_ratio < 1.45): return False
        distances = [math.dist(p, center) for p in pts]
        avg_distance = np.mean(distances)
        if avg_distance < 1e-6: return False
        max_deviation = np.max(np.abs(distances - avg_distance))
        return (max_deviation / avg_distance) < tolerance
    except cv2.error as e: print(f"OpenCV Error circle: {e}"); return False
    except Exception as e: print(f"Error circle: {e}"); return False

def is_rectangle(pts: List[Tuple[int, int]], angle_tolerance: float = 22, epsilon_factor: float = 0.035) -> bool:
    try:
        if len(pts) < MIN_POINTS_RECTANGLE or not is_closed_shape(pts): return False
        np_pts = np.array(pts, dtype=np.float32)
        perimeter = cv2.arcLength(np_pts, True)
        if perimeter < 4 * MIN_SIDE_LENGTH: return False
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(np_pts, epsilon, True)
        if len(approx) != 4: return False
        approx_pts = [tuple(p[0]) for p in approx]
        area = calculate_area(approx_pts)
        if area < MIN_AREA: return False
        sides = [math.dist(approx_pts[i], approx_pts[(i + 1) % 4]) for i in range(4)]
        if min(sides) < MIN_SIDE_LENGTH: return False
        angles = [calculate_angle(approx_pts[i], approx_pts[(i + 1) % 4], approx_pts[(i + 2) % 4]) for i in range(4)]
        angle_deviation = np.max(np.abs(np.array(angles) - 90))
        if angle_deviation > angle_tolerance: return False
        return True
    except Exception as e: print(f"Error rectangle: {e}"); return False

def is_triangle(pts: List[Tuple[int, int]], epsilon_factor: float = 0.05) -> bool:
    try:
        if len(pts) < MIN_POINTS_TRIANGLE or not is_closed_shape(pts): return False
        np_pts = np.array(pts, dtype=np.float32)
        perimeter = cv2.arcLength(np_pts, True)
        if perimeter < 3 * MIN_SIDE_LENGTH: return False
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(np_pts, epsilon, True)
        if len(approx) != 3: return False
        approx_pts = [tuple(p[0]) for p in approx]
        area = calculate_area(approx_pts)
        if area < MIN_AREA: return False
        sides = [math.dist(approx_pts[i], approx_pts[(i + 1) % 3]) for i in range(3)]
        if min(sides) < MIN_SIDE_LENGTH: return False
        angles = [calculate_angle(approx_pts[i], approx_pts[(i + 1) % 3], approx_pts[(i + 2) % 3]) for i in range(3)]
        if not all(15 < angle < 165 for angle in angles): return False
        return True
    except Exception as e: print(f"Error triangle: {e}"); return False

# --- MQTT Callback Functions ---
def on_connect(client, userdata, flags, rc):
    """Callback khi kết nối MQTT thành công."""
    global mqtt_connected
    if rc == 0:
        print(f"Connected to MQTT Broker: {MQTT_BROKER}")
        mqtt_connected = True
    else:
        print(f"Failed to connect to MQTT Broker, return code {rc}")
        mqtt_connected = False

def on_disconnect(client, userdata, rc):
    """Callback khi mất kết nối MQTT."""
    global mqtt_connected
    print(f"Disconnected from MQTT Broker (rc: {rc}). Will attempt to reconnect.")
    mqtt_connected = False
    # Paho client sẽ tự động thử kết nối lại nếu loop đang chạy

def on_publish(client, userdata, mid):
    """Callback sau khi publish (ít dùng hơn)."""
    # print(f"Message Published (mid={mid})")
    pass

# --- Command Processing (Sử dụng MQTT) ---
def clear_queue(q: Queue):
    while True:
        try: q.get_nowait(); q.task_done()
        except Empty: break

def command_processor(q: Queue, mqtt_client: mqtt.Client): # <<<--- Nhận mqtt_client
    """Thread xử lý lệnh từ queue và publish qua MQTT."""
    last_command_time = 0
    while True:
        try:
            command = q.get()
            if command == "EXIT":
                print("Command processor received EXIT signal.")
                break

            current_time = time.time()
            if current_time - last_command_time >= COMMAND_COOLDOWN:
                if mqtt_connected: # <<<--- Chỉ publish khi đang kết nối
                    # Publish lệnh qua MQTT
                    payload = command # Gửi trực tiếp chuỗi lệnh
                    msg_info = mqtt_client.publish(MQTT_TOPIC, payload=payload, qos=0) # QoS 0: At most once
                    msg_info.wait_for_publish(timeout=1.0) # Chờ publish hoàn tất (tùy chọn)

                    if msg_info.is_published():
                        print(f"MQTT Published: '{command}' to topic '{MQTT_TOPIC}'")
                        last_command_time = current_time
                    else:
                         print(f"Failed to publish MQTT message for command '{command}'.")
                         # Có thể thử lại hoặc bỏ qua
                else:
                    print(f"Command '{command}' skipped: MQTT not connected.")
            else:
                print(f"Command '{command}' skipped due to cooldown.")

            q.task_done()
        except TimeoutError:
             print(f"MQTT publish timeout for command '{command}'.")
        except Exception as e:
            print(f"Error in command_processor: {e}")
            try: q.task_done() # Đảm bảo task_done được gọi
            except ValueError: pass

# Hàm thêm điểm (Giữ nguyên)
def add_point(cx: int, cy: int, min_distance: float = MIN_POINT_DISTANCE):
    global points
    if not points or math.dist(points[-1], (cx, cy)) > min_distance:
        points.append((cx, cy))
        if len(points) > MAX_POINTS: points.pop(0)

# --- Main Loop ---
def main():
    global points
    global mqtt_connected # Để cập nhật trạng thái MQTT

    # --- Khởi tạo MQTT Client ---
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_publish = on_publish

    # Cố gắng kết nối lần đầu
    try:
        print(f"Attempting to connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60) # keepalive=60 giây
    except Exception as e:
        print(f"Initial MQTT connection failed: {e}")
        print("Proceeding without MQTT initially. Will retry connection in background.")
        # Chương trình vẫn chạy, loop_start sẽ cố gắng kết nối lại

    # Bắt đầu MQTT loop trong thread riêng để xử lý kết nối/publish/reconnect
    mqtt_client.loop_start() # <<<--- Rất quan trọng

    # --- Khởi động thread xử lý lệnh (truyền MQTT client vào) ---
    cmd_thread = threading.Thread(target=command_processor, args=(command_queue, mqtt_client), daemon=True)
    cmd_thread.start()

    # --- Khởi tạo Camera ---
    cap = cv2.VideoCapture(0)
    if not cap.isOpened(): print("Error: Cannot open camera"); return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera resolution: {frame_width}x{frame_height}")

    # --- Khởi tạo các biến trạng thái ---
    shape_sent_this_gesture = False
    is_drawing_locked = False
    prev_frame_time = 0.0
    startup_time = time.time()
    is_startup = True
    status_text = "Initializing..."
    last_hand_detected_time = 0
    hand_detected_start_time: Optional[float] = None
    can_start_drawing = False

    # --- Cấu hình hiển thị ---
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    font_thickness = 2
    white_color = (255, 255, 255)
    black_color = (0, 0, 0)
    green_color = (0, 255, 0)
    red_color = (0, 0, 255) # Màu đỏ cho trạng thái lỗi/mất kết nối
    purple_color = (255, 0, 255)

    # --- Vòng lặp chính ---
    try: # Bọc vòng lặp chính trong try...finally để đảm bảo dọn dẹp
        while True:
            ret, frame = cap.read()
            if not ret: time.sleep(0.1); continue

            current_frame_time = time.time()
            fps = 1.0 / (current_frame_time - prev_frame_time) if prev_frame_time > 0 else 0
            prev_frame_time = current_frame_time

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False
            results = hands.process(rgb_frame)
            # rgb_frame.flags.writeable = True # Không cần thiết

            # --- Vẽ thông tin cơ bản ---
            cv2.rectangle(frame, (5, 5), (450, 120), black_color, -1) # Tăng chiều cao hộp thông tin
            cv2.putText(frame, f"FPS: {int(fps)}", (10, 30), font, font_scale, white_color, font_thickness)
            cv2.putText(frame, f"Points: {len(points)}", (150, 30), font, font_scale, white_color, font_thickness)
            # Hiển thị trạng thái MQTT
            mqtt_status_text = f"MQTT: {'Connected' if mqtt_connected else 'Disconnected'}"
            mqtt_status_color = green_color if mqtt_connected else red_color
            cv2.putText(frame, mqtt_status_text, (10, 90), font, font_scale, mqtt_status_color, font_thickness)


            # --- Giai đoạn khởi động ---
            if is_startup:
                if current_frame_time - startup_time > STARTUP_DURATION:
                    is_startup = False
                    status_text = "Show hand to draw shape"
                else:
                    status_text = f"Starting... {STARTUP_DURATION - (current_frame_time - startup_time):.1f}s"
                if results.multi_hand_landmarks:
                    for hand_landmarks in results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                cv2.putText(frame, status_text, (10, 60), font, font_scale, green_color, font_thickness)
                cv2.imshow("Draw with finger", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
                continue

            # --- Xử lý chính ---
            hand_currently_detected = bool(results.multi_hand_landmarks)

            if hand_currently_detected:
                last_hand_detected_time = current_frame_time
                hand_landmarks = results.multi_hand_landmarks[0]
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                if hand_detected_start_time is None:
                    hand_detected_start_time = current_frame_time
                    can_start_drawing = False
                    points.clear()
                    shape_sent_this_gesture = False
                    is_drawing_locked = False
                    status_text = f"Hand detected. Waiting {HAND_DETECTION_DRAW_DELAY:.2f}s..."

                wait_elapsed = current_frame_time - hand_detected_start_time
                if not can_start_drawing and wait_elapsed >= HAND_DETECTION_DRAW_DELAY:
                    can_start_drawing = True
                    status_text = "Ready to draw!"

                if can_start_drawing and not is_drawing_locked:
                    status_text = "Drawing..."
                    index_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    cx = int(index_finger_tip.x * frame_width)
                    cy = int(index_finger_tip.y * frame_height)
                    add_point(cx, cy)

                    smoothed_points = smooth_points(points)
                    if len(smoothed_points) > 1:
                        cv2.polylines(frame, [np.array(smoothed_points)], isClosed=False, color=purple_color, thickness=3)

                    min_req_points = min(MIN_POINTS_CIRCLE, MIN_POINTS_RECTANGLE, MIN_POINTS_TRIANGLE)
                    if len(smoothed_points) >= min_req_points and not shape_sent_this_gesture:
                         if is_closed_shape(smoothed_points):
                            command: Optional[str] = None
                            detected_shape = ""
                            if is_rectangle(smoothed_points): command = "RECTANGLE"; detected_shape = "Rectangle"
                            elif is_circle(smoothed_points): command = "CIRCLE"; detected_shape = "Circle"
                            elif is_triangle(smoothed_points): command = "TRIANGLE"; detected_shape = "Triangle"

                            if command:
                                try:
                                    command_queue.put_nowait(command) # Đưa lệnh vào queue để thread kia xử lý
                                    status_text = f"{detected_shape} Detected! Press 'r' to reset."
                                    print(f"Shape '{command}' detected, adding to queue.")
                                    shape_sent_this_gesture = True
                                    is_drawing_locked = True
                                    points.clear()
                                except Exception as e:
                                    status_text = "Cmd Q Full!"
                                    print(f"Queue full?: {e}")

                elif is_drawing_locked:
                    status_text = "Shape sent. Press 'r' to draw again."
                elif not can_start_drawing:
                    remaining_wait = HAND_DETECTION_DRAW_DELAY - wait_elapsed
                    status_text = f"Waiting... {remaining_wait:.1f}s"

            else: # Không phát hiện tay
                if hand_detected_start_time is not None:
                    hand_detected_start_time = None
                    can_start_drawing = False

                if current_frame_time - last_hand_detected_time > NO_HAND_TIMEOUT and len(points) > 0:
                    points.clear()

                if not is_drawing_locked:
                     status_text = "No hand detected. Show hand."
                # else: Giữ nguyên status khóa

            # --- Vẽ status text và hiển thị frame ---
            cv2.putText(frame, status_text, (10, 60), font, font_scale, green_color, font_thickness)
            cv2.imshow("Draw with finger", frame)

            # --- Xử lý phím bấm ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("'q' pressed, exiting...")
                try: command_queue.put_nowait("EXIT")
                except Exception as e: print(f"Queue Error on Exit: {e}")
                break # Thoát vòng lặp chính
            elif key == ord('r'):
                print("'r' pressed, resetting...")
                points.clear()
                clear_queue(command_queue)
                shape_sent_this_gesture = False
                is_drawing_locked = False
                can_start_drawing = False
                hand_detected_start_time = None
                status_text = "Ready to draw. Show hand."

    except Exception as e: # Bắt lỗi không mong muốn trong vòng lặp chính
        print(f"!!!!!!!!!! MAIN LOOP CRITICAL ERROR: {e} !!!!!!!!!!!")
        import traceback
        traceback.print_exc()
    finally: # <<<--- Khối finally đảm bảo dọn dẹp ngay cả khi có lỗi
        # --- Dọn dẹp ---
        print("Cleaning up...")
        print("Stopping MQTT loop...")
        mqtt_client.loop_stop() # Dừng background loop của MQTT
        print("Disconnecting MQTT client...")
        mqtt_client.disconnect()
        print("Releasing camera...")
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        print("Destroying windows...")
        cv2.destroyAllWindows()
        # Gửi tín hiệu EXIT nếu chưa gửi và chờ thread command kết thúc
        try: command_queue.put("EXIT", block=False) # Thử gửi non-blocking
        except: pass # Bỏ qua nếu queue đầy hoặc thread đã dừng
        print("Waiting for command processor thread...")
        if 'cmd_thread' in locals() and cmd_thread.is_alive():
             cmd_thread.join(timeout=1.5)
        print("Exited.")


if __name__ == "__main__":
    # Đảm bảo bạn đang chạy một MQTT Broker (như Mosquitto) tại địa chỉ MQTT_BROKER
    # Ví dụ cài đặt Mosquitto trên Ubuntu/Debian:
    # sudo apt update
    # sudo apt install mosquitto mosquitto-clients
    # sudo systemctl enable mosquitto
    # sudo systemctl start mosquitto
    # Bạn có thể kiểm tra broker bằng cách subscribe dùng mosquitto_sub:
    # mosquitto_sub -h localhost -t "car/command"
    main()