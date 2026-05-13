import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/probe_roboflow.py <image-path>")
        return 2

    api_key = os.getenv("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print("ROBOFLOW_API_KEY is not set.")
        return 2

    model_id = os.getenv(
        "ROBOFLOW_MODEL_ID",
        "new-student-classroom-activity-3-hand-raise-phone-sleep-2-x63gb-6j0xy/6",
    ).strip("/")
    confidence = int(float(os.getenv("ROBOFLOW_CONFIDENCE", "0.10")) * 100)
    overlap = int(float(os.getenv("ROBOFLOW_OVERLAP", "0.45")) * 100)
    query = urllib.parse.urlencode(
        {
            "api_key": api_key,
            "confidence": confidence,
            "overlap": overlap,
            "format": "json",
        }
    )
    url = "https://detect.roboflow.com/{}?{}".format(model_id, query)

    with open(sys.argv[1], "rb") as handle:
        image_data = handle.read()

    request = urllib.request.Request(
        url,
        data=base64.b64encode(image_data),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code)
        print(exc.read().decode("utf-8", errors="replace"))
        return 1

    parsed = json.loads(payload)
    predictions = parsed.get("predictions", [])
    class_counts = Counter(str(item.get("class") or item.get("class_name") or "object") for item in predictions)
    print(
        "ROBOFLOW_ENV:",
        json.dumps(
            {
                "model": model_id,
                "confidence": confidence / 100,
                "overlap": overlap / 100,
                "has_key": bool(api_key),
                "predictions": len(predictions),
                "classes": dict(class_counts),
            },
            ensure_ascii=False,
        ),
    )
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
