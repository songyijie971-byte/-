import time

import cv2
from ultralytics import YOLO

from behavior_core import map_detections_to_behaviors, normalize_detections

model = YOLO("best.onnx", task="detect")

img = cv2.imread("image.png")
timestamp = time.time()

results = model(img, conf=0.25)
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
cv2.imwrite("result.jpg", result_img)
