import requests
import json

url = "https://api.runpod.ai/v2/ppow5bwr1w4nrr/runsync"

# Added the required Authorization header
headers = {
    "Authorization": "Bearer rpa_1XY9XO0MCOQSWK34WS2PS9P90VAX83B3Z4I30FIG10ingd",
    "Content-Type": "application/json"
}

payload = {
    "input": {
        "video_url": "https://raw.githubusercontent.com/ryash072007/test/main/oss_input_video.mp4"
    }
}

print("Dispatching request to local RunPod worker...")
# Passed headers to the post request
response = requests.post(url, json=payload, headers=headers)

# Pretty-print the response
try:
    print(json.dumps(response.json(), indent=4))
except requests.exceptions.JSONDecodeError:
    print(f"Error parsing response. Status Code: {response.status_code}")
    print(response.text)