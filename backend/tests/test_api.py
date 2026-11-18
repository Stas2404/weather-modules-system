import uuid
from datetime import datetime, timedelta, timezone
import httpx
import pytest

BASE_URL = "http://localhost:8000/api/v1"
ADMIN_EMAIL = "admin@nure.ua"
ADMIN_PASSWORD = "AdminPassword123!"


@pytest.mark.asyncio
async def test_full_system_workflow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        # 1. Невдалий вхід -> 401
        bad_login = await client.post(
            "/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong_password"}
        )
        assert bad_login.status_code == 401

        # 2. Успішний вхід адміністратора -> JWT
        login_res = await client.post(
            "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. Створення вимірювального модуля з паспортом
        unique_sn = f"ESP32-TEST-{uuid.uuid4().hex[:6].upper()}"
        mod_res = await client.post(
            "/modules",
            headers=auth_headers,
            json={
                "serial_number": unique_sn,
                "name": "Польовий модуль BME280 #1",
                "status": "active",
                "passport": {
                    "min_temp": -10.0,
                    "max_temp": 40.0,
                    "min_humidity": 10.0,
                    "max_humidity": 85.0,
                    "min_pressure_hpa": 950.0,
                    "max_pressure_hpa": 1050.0,
                    "ip_protection_class": "IP65",
                    "firmware_version": "1.0.4",
                },
            },
        )
        assert mod_res.status_code == 201
        module_id = mod_res.json()["id"]

        # 4. Генерація IoT API-ключа для модуля
        key_res = await client.post(f"/modules/{module_id}/api-keys", headers=auth_headers)
        assert key_res.status_code == 201
        iot_api_key = key_res.json()["raw_api_key"]
        iot_headers = {"X-API-Key": iot_api_key}

        # 5. Створення типу умов та профілю спостереження
        cond_code = f"EXTREME_{uuid.uuid4().hex[:4].upper()}"
        cond_res = await client.post(
            "/condition-types",
            headers=auth_headers,
            json={
                "code": cond_code,
                "name": "Висока вологість та спека",
                "description": "Тестування у кліматичній камері",
            },
        )
        assert cond_res.status_code == 201
        cond_id = cond_res.json()["id"]

        prof_res = await client.post(
            "/profiles",
            headers=auth_headers,
            json={
                "condition_type_id": cond_id,
                "name": "Профіль 10 сек",
                "sampling_interval_sec": 10,
                "alert_margin_percent": 5.0,
            },
        )
        assert prof_res.status_code == 201
        profile_id = prof_res.json()["id"]

        # 6. Запуск сесії випробувань та перевірка заборони дублювання активної сесії (409)
        sess_res = await client.post(
            "/sessions",
            headers=auth_headers,
            json={
                "module_id": module_id,
                "profile_id": profile_id,
                "title": "Тестовий прогін №1",
                "location": "Лабораторія ХНУРЕ",
            },
        )
        assert sess_res.status_code == 201
        session_id = sess_res.json()["id"]

        dup_sess_res = await client.post(
            "/sessions",
            headers=auth_headers,
            json={
                "module_id": module_id,
                "profile_id": profile_id,
                "title": "Паралельна сесія (має відхилитись)",
            },
        )
        assert dup_sess_res.status_code == 409

        # 7. Перевірка захисту IoT-ендпоінта невірним ключем -> 401
        bad_iot = await client.post(
            "/telemetry", headers={"X-API-Key": "invalid_key"}, json={"packets": []}
        )
        assert bad_iot.status_code in (401, 422)

        # 8. Відправка телеметрії: 1 нормальний пакет + 1 дублікат + 1 аномальний (T=48.5°C > 40°C)
        t1 = datetime.now(timezone.utc)
        t2 = t1 + timedelta(seconds=10)
        telem_res = await client.post(
            "/telemetry",
            headers=iot_headers,
            json={
                "packets": [
                    {
                        "packet_id": "pkt-001",
                        "recorded_at": t1.isoformat(),
                        "temperature": 24.5,
                        "humidity": 55.0,
                        "pressure_hpa": 1013.2,
                    },
                    {
                        "packet_id": "pkt-001",  # Дублікат
                        "recorded_at": t1.isoformat(),
                        "temperature": 24.5,
                        "humidity": 55.0,
                        "pressure_hpa": 1013.2,
                    },
                    {
                        "packet_id": "pkt-002",  # Аномалія перегріву
                        "recorded_at": t2.isoformat(),
                        "temperature": 48.5,
                        "humidity": 92.0,
                        "pressure_hpa": 1010.0,
                    },
                ]
            },
        )
        assert telem_res.status_code == 201
        body = telem_res.json()
        assert body["accepted_count"] == 2
        assert body["duplicates_skipped"] == 1
        assert len(body["anomalies_detected"]) == 2  # Перевищено і температуру, і вологість

        # 9. Перевірка агрегованої аналітики (/summary) та CSV-експорту
        sum_res = await client.get(f"/sessions/{session_id}/summary", headers=auth_headers)
        assert sum_res.status_code == 200
        assert sum_res.json()["records_count"] == 2
        assert sum_res.json()["anomalies_count"] == 2

        csv_res = await client.get(
            f"/sessions/{session_id}/telemetry/export?format=csv", headers=auth_headers
        )
        assert csv_res.status_code == 200
        assert "pkt-001" in csv_res.text and "pkt-002" in csv_res.text

        # 10. Запит AI-діагностики (перевірка створення звіту у БД)
        diag_res = await client.post(
            f"/sessions/{session_id}/diagnostics", headers=auth_headers, json={}
        )
        assert diag_res.status_code == 201
        assert diag_res.json()["status"] in ("success", "error")

        # 11. Завершення сесії випробувань
        comp_res = await client.post(f"/sessions/{session_id}/complete", headers=auth_headers)
        assert comp_res.status_code == 200
        assert comp_res.json()["status"] == "completed"