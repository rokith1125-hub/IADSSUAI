import io
import json
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asgi import app  # noqa: E402

SECRET = "ulaga-unavu-jwt-secret-2024"
USER_ID = "Agri_1"
EMAIL = "testuser@example.com"
PER_CALL_TIMEOUT_SECONDS = 420


def mk_token(user_id=USER_ID, email=EMAIL):
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def tiny_jpeg_bytes():
    try:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (224, 224), (120, 80, 40)).save(buf, format="JPEG")
        return buf.getvalue()
    except Exception:
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def _perform_request(client, method, path, headers, params, json_payload, files, follow_redirects=False):
    kwargs = {
        "headers": headers or {},
        "params": params or {},
        "follow_redirects": follow_redirects,
    }
    if json_payload is not None:
        kwargs["json"] = json_payload
    if files is not None:
        kwargs["files"] = files
    return client.request(method, path, **kwargs)


def call(client, method, path, *, headers=None, params=None, json_payload=None, files=None):
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _perform_request,
            client,
            method,
            path,
            headers,
            params,
            json_payload,
            files,
            False,
        )
        try:
            response = future.result(timeout=PER_CALL_TIMEOUT_SECONDS)
        except TimeoutError:
            return {
                "path": path,
                "method": method,
                "status": "timeout",
                "time_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": {"success": False, "error": f"timeout>{PER_CALL_TIMEOUT_SECONDS}s"},
                "resolved": None,
            }

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    try:
        body = response.json()
    except Exception:
        body = response.text[:500]

    resolved = None
    if response.status_code in (307, 308):
        location = response.headers.get("location")
        if location:
            r2_started = time.perf_counter()
            r2 = _perform_request(
                client,
                method,
                location,
                headers,
                params,
                json_payload,
                files,
                True,
            )
            r2_ms = round((time.perf_counter() - r2_started) * 1000, 2)
            try:
                r2_body = r2.json()
            except Exception:
                r2_body = r2.text[:500]
            resolved = {
                "path": location,
                "status": r2.status_code,
                "time_ms": r2_ms,
                "body": r2_body,
            }

    return {
        "path": path,
        "method": method,
        "status": response.status_code,
        "time_ms": elapsed_ms,
        "body": body,
        "resolved": resolved,
    }


def run_and_log(report, key, *args, **kwargs):
    print(f"[RUN] {key}", flush=True)
    result = call(*args, **kwargs)
    report[key] = result
    print(f"[DONE] {key}: status={result['status']} time_ms={result['time_ms']}", flush=True)


def schema_ok(name, result):
    body = result.get("body")
    if not isinstance(body, dict):
        return False, "non-json"

    if name == "login":
        return ("success" in body) and ("token" in body or "error" in body or "message" in body), "expects success + token/error"
    if name == "dashboard":
        return ("success" in body) and ("dashboard" in body or "error" in body), "expects success + dashboard/error"
    if name == "soil_analyze":
        return ("success" in body) and (("data" in body) or ("error" in body)), "expects success + data/error"
    if name == "crop_recommend":
        return ("success" in body) and (("data" in body) or ("error" in body)), "expects success + data/error"
    if name == "crop_select":
        return ("success" in body), "expects success"
    if name == "start_farming":
        return ("success" in body), "expects success"
    if name == "growth_timeline":
        return ("success" in body) and (("timeline" in body) or ("error" in body)), "expects success + timeline/error"
    if name == "fert_today":
        return ("success" in body) and (("action" in body) or ("error" in body)), "expects success + action/error"
    if name == "weather_current":
        return ("success" in body) and (("weather" in body) or ("error" in body)), "expects success + weather/error"
    if name == "weather_forecast":
        return ("success" in body) and (("forecast" in body) or ("error" in body)), "expects success + forecast/error"
    if name == "disease_analyze":
        return ("success" in body), "expects success"
    if name == "disease_history":
        return ("success" in body), "expects success"
    if name == "smart_mandi":
        return ("success" in body) and (("snapshot" in body) or ("message" in body)), "expects success + snapshot/message"
    if name == "news_today":
        return ("success" in body) and (("news" in body) or ("error" in body)), "expects success + news/error"
    if name == "chatbot_ask":
        return ("success" in body) and (("response" in body) or ("error" in body)), "expects success + response/error"
    if name == "settings":
        return ("success" in body) and (("settings" in body) or ("error" in body)), "expects success + settings/error"
    return True, ""


def main():
    token = mk_token()
    headers = {"Authorization": f"Bearer {token}"}

    soil_bytes = tiny_jpeg_bytes()
    disease_bytes = tiny_jpeg_bytes()

    report = {}

    # Skip heavy startup warmup in test harness to keep audit execution bounded.
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()

    try:
        with TestClient(app) as client:
            run_and_log(
                report,
                "login",
                client,
                "POST",
                "/api/auth/login",
                json_payload={"email": EMAIL, "password": "invalid-pass"},
            )

            run_and_log(report, "dashboard", client, "GET", "/api/dashboard", headers=headers)

            run_and_log(
                report,
                "soil_analyze",
                client,
                "POST",
                "/api/soil/analyze",
                headers=headers,
                files={"image": ("soil.jpg", soil_bytes, "image/jpeg")},
            )

            soil_result_id = None
            soil_body = report["soil_analyze"].get("body")
            if isinstance(soil_body, dict):
                data = soil_body.get("data") or {}
                soil_result_id = data.get("analysis_id") or ((data.get("result") or {}).get("result_id"))

            recommend_params = {"soil_result_id": soil_result_id} if soil_result_id else {}
            run_and_log(
                report,
                "crop_recommend",
                client,
                "GET",
                "/api/crop/recommend",
                headers=headers,
                params=recommend_params,
            )

            selected_crop = "Rice"
            rec_body = report["crop_recommend"].get("body")
            if isinstance(rec_body, dict):
                recs = ((rec_body.get("data") or {}).get("recommendations") or [])
                for rec in recs:
                    name = (rec or {}).get("crop_name")
                    if name and str(name).strip().lower() != "custom crop":
                        selected_crop = name
                        break

            run_and_log(
                report,
                "crop_select",
                client,
                "POST",
                "/api/crop/select",
                headers=headers,
                json_payload={"crop_name": selected_crop, "custom_crop": False},
            )

            run_and_log(
                report,
                "start_farming",
                client,
                "POST",
                "/api/crop/start-farming",
                headers=headers,
                json_payload={},
            )

            run_and_log(report, "growth_timeline", client, "GET", "/api/growth/timeline", headers=headers)
            run_and_log(report, "fert_today", client, "GET", "/api/fertilizer/today", headers=headers)
            run_and_log(report, "weather_current", client, "GET", "/api/weather/current", headers=headers)
            run_and_log(report, "weather_forecast", client, "GET", "/api/weather/forecast", headers=headers)

            run_and_log(
                report,
                "disease_analyze",
                client,
                "POST",
                "/api/disease/analyze",
                headers=headers,
                files={"image": ("disease.jpg", disease_bytes, "image/jpeg")},
            )
            run_and_log(report, "disease_history", client, "GET", "/api/disease/history", headers=headers)

            run_and_log(report, "smart_mandi", client, "GET", "/api/smart-mandi/snapshot", headers=headers)
            run_and_log(report, "news_today", client, "GET", "/api/news/today", headers=headers)

            run_and_log(
                report,
                "chatbot_ask",
                client,
                "POST",
                "/api/chatbot/ask",
                headers=headers,
                json_payload={"question": "What should I do today for my crop?", "language": "en"},
            )
            run_and_log(report, "settings", client, "GET", "/api/settings", headers=headers)

            run_and_log(report, "dashboard_unauthorized", client, "GET", "/api/dashboard")
            run_and_log(
                report,
                "soil_invalid_file",
                client,
                "POST",
                "/api/soil/analyze",
                headers=headers,
                files={"image": ("bad.txt", b"not-an-image", "text/plain")},
            )
            run_and_log(
                report,
                "chatbot_empty",
                client,
                "POST",
                "/api/chatbot/ask",
                headers=headers,
                json_payload={"question": "   "},
            )
    finally:
        app.router.on_startup.extend(startup_handlers)

    checks = {}
    for name in [
        "login",
        "dashboard",
        "soil_analyze",
        "crop_recommend",
        "crop_select",
        "start_farming",
        "growth_timeline",
        "fert_today",
        "weather_current",
        "weather_forecast",
        "disease_analyze",
        "disease_history",
        "smart_mandi",
        "news_today",
        "chatbot_ask",
        "settings",
    ]:
        ok, note = schema_ok(name, report[name])
        checks[name] = {"schema_ok": ok, "note": note}

    out_path = ROOT / "tests" / "_reaudit_results.json"
    out_path.write_text(json.dumps({"report": report, "checks": checks}, indent=2, default=str), encoding="utf-8")
    print(f"RESULT_FILE={out_path}")


if __name__ == "__main__":
    main()
