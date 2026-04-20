from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional


BEHAVIOR_DISPLAY_NAMES = {
    "low_head": "Low Head",
    "hand_raise": "Hand Raise",
    "sleep": "Sleep",
    "turn_talk": "Turn Talk",
    "head_up": "Head Up",
}


# The repo does not include the original class-label file for best.onnx.
# We therefore preserve the existing prototype's empirical class-id mapping:
# 0/5 were previously counted as "phone" related behaviors, and are promoted
# here to the more presentation-friendly "low_head" behavior.
# 4/8/9 continue to map to hand raising, sleeping, and talking/turning.
CLASS_BEHAVIOR_MAP = {
    0: "low_head",
    4: "hand_raise",
    5: "low_head",
    8: "sleep",
    9: "turn_talk",
}


DEFAULT_BEHAVIOR_RULES = {
    "low_head": {
        "min_consecutive_frames": 4,
        "alert_after_seconds": 2.5,
        "alert_enabled": True,
    },
    "hand_raise": {
        "min_consecutive_frames": 2,
        "alert_after_seconds": None,
        "alert_enabled": False,
    },
    "sleep": {
        "min_consecutive_frames": 6,
        "alert_after_seconds": 4.0,
        "alert_enabled": True,
    },
    "turn_talk": {
        "min_consecutive_frames": 4,
        "alert_after_seconds": 3.0,
        "alert_enabled": True,
    },
    "head_up": {
        "min_consecutive_frames": 3,
        "alert_after_seconds": None,
        "alert_enabled": False,
    },
}

BEHAVIOR_RULES = {
    key: dict(value) for key, value in DEFAULT_BEHAVIOR_RULES.items()
}


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]
    timestamp: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class FrameBehavior:
    behavior_key: str
    behavior_name: str
    count: int
    confidence: float
    timestamp: float
    source_class_ids: List[int]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def normalize_detections(result, class_names, timestamp: float) -> List[Detection]:
    detections: List[Detection] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections

    for box in boxes:
        cls_id = int(box.cls.item())
        confidence = float(box.conf.item())
        xyxy = box.xyxy[0].tolist()
        class_name = class_names.get(cls_id, f"class_{cls_id}")
        detections.append(
            Detection(
                class_id=cls_id,
                class_name=class_name,
                confidence=confidence,
                bbox=[float(value) for value in xyxy],
                timestamp=timestamp,
            )
        )

    return detections


def map_detections_to_behaviors(
    detections: List[Detection],
) -> Dict[str, FrameBehavior]:
    grouped: Dict[str, List[Detection]] = {}
    for detection in detections:
        behavior_key = CLASS_BEHAVIOR_MAP.get(detection.class_id)
        if behavior_key is None:
            continue
        grouped.setdefault(behavior_key, []).append(detection)

    frame_behaviors: Dict[str, FrameBehavior] = {}
    for behavior_key, items in grouped.items():
        best_confidence = max(item.confidence for item in items)
        source_class_ids = sorted({item.class_id for item in items})
        frame_behaviors[behavior_key] = FrameBehavior(
            behavior_key=behavior_key,
            behavior_name=BEHAVIOR_DISPLAY_NAMES[behavior_key],
            count=len(items),
            confidence=best_confidence,
            timestamp=items[0].timestamp,
            source_class_ids=source_class_ids,
        )

    # Keep a placeholder interface for head-up behavior until the model or
    # rule set provides enough signal to infer it reliably.
    if "head_up" not in frame_behaviors:
        fallback_timestamp = detections[0].timestamp if detections else 0.0
        frame_behaviors["head_up"] = FrameBehavior(
            behavior_key="head_up",
            behavior_name=BEHAVIOR_DISPLAY_NAMES["head_up"],
            count=0,
            confidence=0.0,
            timestamp=fallback_timestamp,
            source_class_ids=[],
        )

    return frame_behaviors


class BehaviorTemporalAnalyzer:
    def __init__(self, behavior_rules: Dict[str, Dict[str, object]]):
        self.behavior_rules = behavior_rules
        self.state = {
            key: {
                "consecutive_frames": 0,
                "active_count": 0,
                "start_timestamp": None,
                "last_timestamp": None,
                "stable": False,
                "duration_seconds": 0.0,
                "confidence": 0.0,
                "alert_active": False,
                "alert_emitted": False,
            }
            for key in behavior_rules
        }

    def update(
        self,
        frame_behaviors: Dict[str, FrameBehavior],
        timestamp: float,
        alert_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> Dict[str, object]:
        stable_counts: Dict[str, int] = {}
        durations: Dict[str, float] = {}
        active_alerts: List[Dict[str, object]] = []
        triggered_alerts: List[Dict[str, object]] = []
        behavior_details: Dict[str, Dict[str, object]] = {}

        for behavior_key, rule in self.behavior_rules.items():
            frame_behavior = frame_behaviors.get(behavior_key)
            count = frame_behavior.count if frame_behavior else 0
            confidence = frame_behavior.confidence if frame_behavior else 0.0

            behavior_state = self.state[behavior_key]
            if count > 0:
                behavior_state["consecutive_frames"] += 1
                behavior_state["active_count"] = count
                behavior_state["confidence"] = confidence
                if behavior_state["start_timestamp"] is None:
                    behavior_state["start_timestamp"] = timestamp
                behavior_state["last_timestamp"] = timestamp
            else:
                behavior_state["consecutive_frames"] = 0
                behavior_state["active_count"] = 0
                behavior_state["stable"] = False
                behavior_state["duration_seconds"] = 0.0
                behavior_state["confidence"] = 0.0
                behavior_state["alert_active"] = False
                behavior_state["alert_emitted"] = False
                behavior_state["start_timestamp"] = None
                behavior_state["last_timestamp"] = timestamp

            min_frames = int(rule["min_consecutive_frames"])
            if behavior_state["consecutive_frames"] >= min_frames and count > 0:
                behavior_state["stable"] = True
                behavior_state["duration_seconds"] = (
                    timestamp - behavior_state["start_timestamp"]
                    if behavior_state["start_timestamp"] is not None
                    else 0.0
                )
            elif count > 0:
                behavior_state["stable"] = False

            alert_after_seconds = rule["alert_after_seconds"]
            behavior_state["alert_active"] = bool(
                behavior_state["stable"]
                and rule["alert_enabled"]
                and alert_after_seconds is not None
                and behavior_state["duration_seconds"] >= alert_after_seconds
            )

            stable_counts[behavior_key] = (
                behavior_state["active_count"] if behavior_state["stable"] else 0
            )
            durations[behavior_key] = round(behavior_state["duration_seconds"], 1)
            behavior_details[behavior_key] = {
                "name": BEHAVIOR_DISPLAY_NAMES[behavior_key],
                "current_count": count,
                "stable_count": stable_counts[behavior_key],
                "consecutive_frames": behavior_state["consecutive_frames"],
                "duration_seconds": durations[behavior_key],
                "stable": behavior_state["stable"],
                "confidence": round(behavior_state["confidence"], 3),
                "alert_active": behavior_state["alert_active"],
            }

            if behavior_state["alert_active"]:
                alert_payload = {
                    "behavior_key": behavior_key,
                    "behavior_name": BEHAVIOR_DISPLAY_NAMES[behavior_key],
                    "duration_seconds": durations[behavior_key],
                    "count": stable_counts[behavior_key],
                    "timestamp": timestamp,
                }
                active_alerts.append(alert_payload)
                if not behavior_state["alert_emitted"]:
                    behavior_state["alert_emitted"] = True
                    triggered_alerts.append(alert_payload)
                    if alert_callback is not None:
                        alert_callback(alert_payload)
            elif not behavior_state["alert_active"]:
                behavior_state["alert_emitted"] = False

        return {
            "stable_counts": stable_counts,
            "durations": durations,
            "active_alerts": active_alerts,
            "triggered_alerts": triggered_alerts,
            "behavior_details": behavior_details,
        }
