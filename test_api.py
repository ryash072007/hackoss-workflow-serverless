import requests
import json

url = "http://localhost:8000/runsync"

payload = {
    "input": {
        "video_url": "https://raw.githubusercontent.com/ryash072007/test/main/oss_input_video.mp4"
    }
}

print("Dispatching request to local RunPod worker...")
response = requests.post(url, json=payload)

# Pretty-print the response
try:
    print(json.dumps(response.json(), indent=4))
except requests.exceptions.JSONDecodeError:
    print(f"Error parsing response. Status Code: {response.status_code}")
    print(response.text)