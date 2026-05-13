from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import cv2


DEFAULT_ROBOFLOW_MODEL_ID = (
    "new-student-classroom-activity-3-hand-raise-phone-sleep-2-x63gb-6j0xy/6"
)


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "debug"}


class _Scalar:
    def __init__(self, value: float) -> None:
        self._value = value

    def item(self):
        return self._value


class _TensorRow:
    def __init__(self, values: Iterable[float]) -> None:
        self._values = list(values)

    def tolist(self) -> List[float]:
        return list(self._values)


class _Box:
    def __init__(self, class_id: int, confidence: float, bbox: List[float]) -> None:
        self.cls = _Scalar(class_id)
        self.conf = _Scalar(confidence)
        self.xyxy = [_TensorRow(bbox)]


class _Boxes:
    def __init__(self, boxes: List[_Box]) -> None:
        self._boxes = boxes

    def __iter__(self):
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)


@dataclass(frozen=True)
class _Prediction:
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]


class RoboflowResult:
    def __init__(self, frame, predictions: List[_Prediction]) -> None:
        self._frame = frame
        self._predictions = predictions
        self.boxes = _Boxes(
            [_Box(item.class_id, item.confidence, item.bbox) for item in predictions]
        )

    def plot(self):
        annotated = self._frame.copy()
        for prediction in self._predictions:
            x1, y1, x2, y2 = [int(value) for value in prediction.bbox]
            label = "{} {:.2f}".format(prediction.class_name, prediction.confidence)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 255), 2)
            cv2.putText(
                annotated,
                label,
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 220, 255),
                2,
            )
        return annotated


class RoboflowHostedModel:
    def __init__(
        self,
        api_key: str,
        model_id: str = DEFAULT_ROBOFLOW_MODEL_ID,
        api_url: str = "https://detect.roboflow.com",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("ROBOFLOW_API_KEY is required when INFERENCE_PROVIDER=roboflow")
        self.api_key = api_key
        self.model_id = model_id.strip("/")
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.names: Dict[int, str] = {}
        self._name_to_id: Dict[str, int] = {}

    @classmethod
    def from_env(cls):
        timeout_raw = os.getenv("ROBOFLOW_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = max(1.0, float(timeout_raw))
        except (TypeError, ValueError):
            timeout_seconds = 20.0
        return cls(
            api_key=os.getenv("ROBOFLOW_API_KEY", "").strip(),
            model_id=os.getenv("ROBOFLOW_MODEL_ID", DEFAULT_ROBOFLOW_MODEL_ID).strip(),
            api_url=os.getenv("ROBOFLOW_API_URL", "https://detect.roboflow.com").strip(),
            timeout_seconds=timeout_seconds,
        )

    def _class_id_for(self, class_name: str, explicit_class_id: Any = None) -> int:
        if explicit_class_id is not None:
            try:
                class_id = int(explicit_class_id)
                self.names.setdefault(class_id, class_name)
                self._name_to_id.setdefault(class_name.lower(), class_id)
                return class_id
            except (TypeError, ValueError):
                pass

        normalized = class_name.lower()
        if normalized not in self._name_to_id:
            class_id = len(self._name_to_id)
            self._name_to_id[normalized] = class_id
            self.names[class_id] = class_name
        return self._name_to_id[normalized]

    def _build_url(self, conf: float, iou: float) -> str:
        conf = _read_float_env("ROBOFLOW_CONFIDENCE", conf)
        iou = _read_float_env("ROBOFLOW_OVERLAP", iou)
        confidence = int(round(max(0.0, min(1.0, float(conf))) * 100))
        overlap = int(round(max(0.0, min(1.0, float(iou))) * 100))
        query = urllib.parse.urlencode(
            {
                "api_key": self.api_key,
                "confidence": confidence,
                "overlap": overlap,
                "format": "json",
            }
        )
        return "{}/{}?{}".format(self.api_url, self.model_id, query)

    def _request_predictions(self, frame, conf: float, iou: float) -> Dict[str, Any]:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise ValueError("Failed to encode frame for Roboflow inference")

        request = urllib.request.Request(
            self._build_url(conf=conf, iou=iou),
            data=base64.b64encode(encoded.tobytes()),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "Roboflow inference failed with HTTP {}: {}".format(exc.code, body[:300])
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Roboflow inference request failed: {}".format(exc)) from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Roboflow returned a non-JSON response: {}".format(payload[:300])
            ) from exc

    def predict(self, source, conf=0.35, iou=0.45, **kwargs):
        response = self._request_predictions(source, conf=conf, iou=iou)
        raw_predictions = response.get("predictions", [])
        if _read_bool_env("ROBOFLOW_DEBUG", False):
            print(
                "ROBOFLOW_RAW_RESPONSE:",
                json.dumps(response, ensure_ascii=False, default=str),
                flush=True,
            )
            print(
                "ROBOFLOW_PREDICTIONS:",
                json.dumps(raw_predictions, ensure_ascii=False, default=str),
                flush=True,
            )
        predictions = []
        for item in raw_predictions:
            class_name = str(item.get("class") or item.get("class_name") or "object")
            class_id = self._class_id_for(class_name, item.get("class_id"))
            x_center = float(item.get("x", 0.0))
            y_center = float(item.get("y", 0.0))
            width = float(item.get("width", 0.0))
            height = float(item.get("height", 0.0))
            x1 = max(0.0, x_center - width / 2.0)
            y1 = max(0.0, y_center - height / 2.0)
            x2 = max(0.0, x_center + width / 2.0)
            y2 = max(0.0, y_center + height / 2.0)
            predictions.append(
                _Prediction(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(item.get("confidence", 0.0)),
                    bbox=[x1, y1, x2, y2],
                )
            )
        return [RoboflowResult(source, predictions)]


def build_detection_model(runtime_config):
    if getattr(runtime_config, "inference_provider", "local") == "roboflow":
        return RoboflowHostedModel.from_env()

    from ultralytics import YOLO

    return YOLO(runtime_config.model_path, task="detect")
