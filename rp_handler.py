import runpod
import subprocess
import threading
import time
import requests
import json
import uuid
import os
from urllib.parse import urlparse

# ComfyUI server setup
COMFYUI_DIR = "/ComfyUI"
COMFYUI_URL = "http://127.0.0.1:8188"

def start_comfyui():
    """Starts the ComfyUI server."""
    os.chdir(COMFYUI_DIR)
    command = "python3 main.py --listen"
    server_process = subprocess.Popen(command.split())
    return server_process

def check_server_ready(url):
    """Check if the server is ready to accept requests."""
    while True:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print("ComfyUI server is ready.")
                break
        except requests.exceptions.ConnectionError:
            print("Waiting for ComfyUI server...")
            time.sleep(1)

def queue_prompt(prompt):
    """Queues a prompt to the ComfyUI server."""
    with requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": prompt}) as response:
        response.raise_for_status()
        return response.json()

def get_history(prompt_id):
    """Gets the history for a given prompt ID."""
    with requests.get(f"{COMFYUI_URL}/history/{prompt_id}") as response:
        response.raise_for_status()
        return response.json()

def get_video(filename, subfolder, folder_type):
    """Gets a video from the ComfyUI server."""
    with requests.get(f"{COMFYUI_URL}/view", params={"filename": filename, "subfolder": subfolder, "type": folder_type}) as response:
        response.raise_for_status()
        return response.content

def download_video(url, save_path):
    """Downloads a video from a URL."""
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return save_path

def handler(event):
    """The serverless handler function."""
    print("Worker Start")
    
    input_data = event['input']
    video_url = input_data.get('video_url')

    if not video_url:
        return {"error": "video_url not provided"}

    # Download the input video
    video_filename = os.path.basename(urlparse(video_url).path)
    input_video_path = os.path.join(COMFYUI_DIR, "input", video_filename)
    download_video(video_url, input_video_path)

    # Load the workflow
    with open("oss_stickman_api.json", 'r') as f:
        prompt = json.load(f)

    # Update the video path in the workflow
    # Node 154 is the LoadVideo node
    prompt["154"]["inputs"]["video"] = video_filename

    # Queue the prompt
    prompt_id = queue_prompt(prompt)['prompt_id']
    
    # Wait for the output
    output_video = None
    while not output_video:
        history = get_history(prompt_id)
        if prompt_id in history and 'outputs' in history[prompt_id]:
            outputs = history[prompt_id]['outputs']
            # Find the output video from node 167 (VHS_VideoCombine)
            if "167" in outputs and "videos" in outputs["167"]:
                video_data = outputs["167"]["videos"][0]
                video_content = get_video(video_data['filename'], video_data['subfolder'], video_data['type'])
                
                # Save the output video
                output_filename = f"output_{uuid.uuid4()}.mp4"
                output_path = os.path.join("/tmp", output_filename)
                with open(output_path, "wb") as f:
                    f.write(video_content)
                
                output_video = output_path
                print(f"Output video saved to: {output_video}")
                break
        time.sleep(1)

    # TODO: Upload the output video to a cloud storage and return the URL
    # For now, we'll just return a success message
    
    return {"status": "success", "output_path": output_video}


if __name__ == '__main__':
    # Start ComfyUI in a separate thread
    server_thread = threading.Thread(target=start_comfyui)
    server_thread.daemon = True
    server_thread.start()

    # Wait for the server to be ready
    check_server_ready(COMFYUI_URL)
    
    # Start the RunPod serverless worker
    runpod.serverless.start({'handler': handler})
