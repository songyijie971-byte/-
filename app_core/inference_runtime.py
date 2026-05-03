from __future__ import annotations

import inspect
import os
from functools import lru_cache
from typing import Any


def _read_device_override() -> str:
    return os.getenv("YOLO_DEVICE") or os.getenv("INFERENCE_DEVICE") or "auto"


@lru_cache(maxsize=1)
def resolve_inference_device() -> Any:
    """Return the Ultralytics device preference: CUDA first, CPU fallback."""
    override = _read_device_override().strip().lower()
    if override and override not in {"auto", "gpu", "cuda"}:
        return override

    try:
        import torch

        if torch.cuda.is_available():
            return 0
    except Exception:
        pass

    return "cpu"


def inference_device_label(device: Any | None = None) -> str:
    device = resolve_inference_device() if device is None else device
    if isinstance(device, int) or str(device).lower().startswith(("cuda", "gpu")):
        return "gpu"
    return "cpu"


def _predict_accepts_device(model: Any) -> bool:
    try:
        signature = inspect.signature(model.predict)
    except (TypeError, ValueError):
        return True
    return "device" in signature.parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def predict_with_preferred_device(model: Any, source: Any, logger: Any = None, **kwargs):
    device = resolve_inference_device()
    if _predict_accepts_device(model):
        try:
            return model.predict(source, device=device, **kwargs)
        except Exception as exc:
            if device == "cpu" or os.getenv("YOLO_DEVICE_STRICT", "").strip() == "1":
                raise
            if logger is not None:
                logger.warning(
                    "GPU inference failed, falling back to CPU: %s",
                    exc,
                    exc_info=True,
                )
            return model.predict(source, device="cpu", **kwargs)

    return model.predict(source, **kwargs)
