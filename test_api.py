import requests
import json
import time

# --- Configuration ---
ENDPOINT_ID = "ppow5bwr1w4nrr"
BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"
AUTH_TOKEN = "rpa_1XY9XO0MCOQSWK34WS2PS9P90VAX83B3Z4I30FIG10ingd"

headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "input": {
        "video_url": "https://raw.githubusercontent.com/ryash072007/test/main/oss_input_video.mp4"
    }
}

# --- 1. Initial Job Dispatch (/run) ---
run_url = f"{BASE_URL}/run"
print(f"POST {run_url}")

try:
    response = requests.post(run_url, json=payload, headers=headers)
    run_response_json = response.json()
except (requests.exceptions.JSONDecodeError, requests.exceptions.RequestException) as e:
    print(f"Network error or invalid JSON during dispatch: {e}")
    exit(1)

# Print full initial response schema
print("\n=== INITIAL RUN ENDPOINT RESPONSE ===")
print(json.dumps(run_response_json, indent=4))
print("======================================\n")

job_id = run_response_json.get("id")
if not job_id:
    print("Error: Extraction of 'id' failed from the initialization payload.")
    exit(1)

# --- 2. Polling Loop (/status/{id}) ---
status_url = f"{BASE_URL}/status/{job_id}"
terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}

print(f"GET {status_url}")
print("Starting execution tracking loop...")

while True:
    try:
        status_response = requests.get(status_url, headers=headers)
        status_json = status_response.json()
    except (requests.exceptions.JSONDecodeError, requests.exceptions.RequestException) as e:
        print(f"\n[Warning] Transient network issue encountered: {e}. Retrying...")
        time.sleep(5)
        continue

    current_status = status_json.get("status")
    print(f"Tracking Job [{job_id}] | Status: {current_status}")

    if current_status in terminal_states:
        print("\n=== FINAL STATUS ENDPOINT RESPONSE ===")
        print(json.dumps(status_json, indent=4))
        print("========================================")
        break

    time.sleep(3)