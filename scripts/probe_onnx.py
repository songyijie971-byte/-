import time
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
from ultralytics import YOLO

from app_core.inference_runtime import predict_with_preferred_device
from behavior_core import map_detections_to_behaviors, normalize_detections

MODEL_PATH = ROOT_DIR / "best.onnx"
SAMPLE_IMAGE_PATH = ROOT_DIR / "samples" / "image.png"
OUTPUT_DIR = ROOT_DIR / "model_probe_outputs"

model = YOLO(str(MODEL_PATH), task="detect")

img = cv2.imread(str(SAMPLE_IMAGE_PATH))
if img is None:
    raise FileNotFoundError(f"Could not read sample image: {SAMPLE_IMAGE_PATH}")
timestamp = time.time()

results = predict_with_preferred_device(model, img, conf=0.25)
detections = normalize_detections(results[0], model.names, timestamp)
frame_behaviors = map_detections_to_behaviors(detections)

print("Normalized detections:")
for detection in detections:
    print(
        f"class_id={detection.class_id}, "
        f"class_name={detection.class_name}, "
        f"confidence={detection.confidence:.3f}, "
        f"bbox={detection.bbox}"
    )

print("\nFrame behaviors:")
for behavior in frame_behaviors.values():
    print(
        f"behavior={behavior.behavior_name}, "
        f"count={behavior.count}, "
        f"confidence={behavior.confidence:.3f}, "
        f"source_class_ids={behavior.source_class_ids}"
    )

result_img = results[0].plot()
OUTPUT_DIR.mkdir(exist_ok=True)
cv2.imwrite(str(OUTPUT_DIR / "result.jpg"), result_img)
