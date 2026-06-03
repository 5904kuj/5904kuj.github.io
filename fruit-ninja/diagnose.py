"""카메라/손 추적 진단 스크립트. 창에 웹캠 화면 + 손 위치를 표시합니다."""
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import time
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")

print("=== 카메라 목록 탐색 ===")
for i in range(4):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ok, f = cap.read()
        print(f"  CAM_INDEX={i}  {'OK - 사용 가능' if ok else '열림 but 프레임 없음'}")
    else:
        print(f"  CAM_INDEX={i}  없음")
    cap.release()

print("\n사용할 CAM_INDEX를 입력하세요 (보통 0): ", end="")
idx = input().strip()
idx = int(idx) if idx.isdigit() else 0

options = mp_vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=mp_vision.RunningMode.VIDEO,
    num_hands=2,
    min_hand_detection_confidence=0.4,
    min_hand_presence_confidence=0.4,
    min_tracking_confidence=0.4,
)

cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print(f"\nCAM {idx} 열림. 손을 화면 앞에 두세요. 'Q'로 종료.\n")

with mp_vision.HandLandmarker.create_from_options(options) as lm:
    while True:
        ok, frame = cap.read()
        if not ok:
            print("프레임 읽기 실패")
            break
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ts = int(time.perf_counter() * 1000)
        result = lm.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

        h, w = frame.shape[:2]
        if result.hand_landmarks:
            for i, lm_list in enumerate(result.hand_landmarks):
                tip = lm_list[8]
                x, y = int(tip.x * w), int(tip.y * h)
                cv2.circle(frame, (x, y), 14, (0, 255, 0), -1)
                cv2.putText(frame, f"Hand{i} ({x},{y})",
                            (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 255, 0), 2)
            print(f"\r손 감지: {len(result.hand_landmarks)}개     ", end="")
        else:
            cv2.putText(frame, "손이 감지되지 않음 - 손을 카메라 앞에 두세요",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            print("\r손 없음...           ", end="")

        cv2.imshow("진단 (Q로 종료)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
print("\n진단 완료")
