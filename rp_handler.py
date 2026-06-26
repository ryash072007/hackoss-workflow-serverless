import runpod
import subprocess
import threading
import time
import requests
import json
import uuid
import os
import sys
import boto3
from botocore.config import Config
from urllib.parse import urlparse

# ComfyUI server setup
COMFYUI_DIR = "/ComfyUI"
COMFYUI_URL = "http://127.0.0.1:8188"

# Global tracking variable for the process object
comfy_process = None

def start_comfyui():
    """Starts the ComfyUI server and assigns it to a global variable."""
    global comfy_process
    command = "python3 main.py --listen"
    # Execute the subprocess in COMFYUI_DIR without changing the global process directory
    comfy_process = subprocess.Popen(command.split(), cwd=COMFYUI_DIR)
    
    # Block until process completes (runs in daemon thread, but allows us to capture early exit)
    comfy_process.wait()
    print(f"[CRITICAL] ComfyUI background process exited with code {comfy_process.returncode}")

def check_server_ready(url):
    """Check if the server is ready to accept requests, while validating process health."""
    global comfy_process
    while True:
        # Crucial Defensive Fix: If the process died, exit immediately to stop billing
        if comfy_process and comfy_process.poll() is not None:
            print(f"[FATAL] ComfyUI process crashed with code {comfy_process.poll()} during startup.")
            sys.exit(1)

        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print("ComfyUI server is ready.")
                break
        except requests.exceptions.RequestException:
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

def download_video(url, save_path):
    """Downloads a video from a URL."""
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return save_path

# --- Backend Telemetry ---
def update_job_status(job_id, status, percent, object_key=None, error_msg=None):
    """Pushes job state to your custom backend contract."""
    BACKEND_API_URL = os.environ.get('BACKEND_API_URL')
    BACKEND_API_KEY = os.environ.get('BACKEND_API_KEY')
    if not BACKEND_API_URL:
        print("Warning: BACKEND_API_URL not set. Cannot report status.")
        return

    endpoint = f"{BACKEND_API_URL.rstrip('/')}/jobs/{job_id}"
    
    payload = {
        "percentCompleted": percent,
        "jobStatus": status
    }
    
    if object_key:
        payload["stickmanifiedS3ObjectKey"] = object_key
    if error_msg:
        payload["errorMessage"] = error_msg

    X_ADMIN_TOKEN = os.environ.get("X_ADMIN_TOKEN")

    headers = {
        "Content-Type": "application/json",
        "X-ADMIN-TOKEN": X_ADMIN_TOKEN
    }
    
    print(f"[DEBUG] Sending request to: {endpoint}")
    print(f"[DEBUG] Loaded X_ADMIN_TOKEN from environment: {X_ADMIN_TOKEN}")

    try:
        response = requests.put(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"Successfully updated backend job {job_id} to {status}")
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL: Failed to update backend job status for {job_id}. Error: {str(e)}")

def handler(event):
    """The serverless handler function."""
    global comfy_process
    print("Worker Start")
    
    # Fail-fast check: Did ComfyUI crash while sitting idle between jobs?
    if comfy_process and comfy_process.poll() is not None:
        err = f"ComfyUI engine was dead on arrival. Code: {comfy_process.poll()}"
        print(f"[FATAL] {err}")
        sys.exit(2) # Crashing the handler forces RunPod to cycle the pod instance

    input_data = event.get('input', {})
    job_id = input_data.get('jobId') 
    object_key = input_data.get('objectKey')

    if not object_key:
        err = "objectKey not provided in input payload"
        update_job_status(job_id, "FAILED", 0, error_msg=err)
        return {"error": "object_key not provided"}

    update_job_status(job_id, "IN_PROGRESS", 5)
    bucket_name = os.environ.get('SUPABASE_S3_BUCKET')
    
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=os.environ.get('SUPABASE_S3_ENDPOINT'),
            aws_access_key_id=os.environ.get('SUPABASE_S3_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('SUPABASE_S3_SECRET_KEY'),
            region_name=os.environ.get('SUPABASE_S3_REGION', 'auto')
        )
    except Exception as e:
        err = f"Failed to initialize S3 client: {str(e)}"
        update_job_status(job_id, "FAILED", 10, error_msg=err)
        return {"error": f"Failed to initialize S3 client: {str(e)}"}

    video_filename = os.path.basename(object_key)
    input_video_path = os.path.join(COMFYUI_DIR, "input", video_filename)
    
    try:
        print(f"Downloading {object_key} from S3...")
        s3_client.download_file(bucket_name, object_key, input_video_path)
        update_job_status(job_id, "IN_PROGRESS", 15)
    except Exception as e:
        err = f"Failed to download video from S3: {str(e)}"
        update_job_status(job_id, "FAILED", 10, error_msg=err)
        return {"error": f"Failed to download video from S3: {str(e)}"}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    workflow_path = os.path.join(script_dir, "oss_stickman_api.json")
    
    with open(workflow_path, 'r') as f:
        prompt = json.load(f)

    prompt["154"]["inputs"]["video"] = video_filename

    try:
        prompt_id = queue_prompt(prompt)['prompt_id']
    except Exception as e:
        err = f"Failed to submit workflow task to ComfyUI backend: {str(e)}"
        update_job_status(job_id, "FAILED", 18, error_msg=err)
        return {"error": err}
        
    update_job_status(job_id, "IN_PROGRESS", 20)

    # Wait for the output
    while True:
        # Operational loop insurance: stop checking history if ComfyUI crashes mid-inference
        if comfy_process and comfy_process.poll() is not None:
            err = "ComfyUI process crashed mid-execution."
            update_job_status(job_id, "FAILED", 50, error_msg=err)
            sys.exit(3)

        try:
            history = get_history(prompt_id)
        except Exception as e:
            print(f"Polling history error (retrying): {str(e)}")
            time.sleep(1)
            continue
        
        if prompt_id in history:
            update_job_status(job_id, "IN_PROGRESS", 90)
            outputs = history[prompt_id].get('outputs', {})
            
            for node_output in outputs.values():
                media_list = node_output.get('gifs') or node_output.get('videos')
                
                if media_list and media_list[0].get('type') == 'output':
                    filename = media_list[0]['filename']
                    physical_path = os.path.join(COMFYUI_DIR, "output", filename)
                    
                    if os.path.exists(physical_path):
                        print(f"Success. Video located at: {physical_path}")
                        
                        upload_filename = f"{job_id}.mp4"
                        bucket_name = os.environ.get('SUPABASE_S3_BUCKET_OUTPUT')
                        
                        s3_client.upload_file(physical_path, bucket_name, upload_filename, ExtraArgs={'ContentType': 'video/mp4'})
                        
                        os.remove(physical_path)
                        if os.path.exists(input_video_path):
                            os.remove(input_video_path)
                        
                        update_job_status(job_id, "COMPLETED", 100, object_key=upload_filename)

                        return {"status": "success"}
            
            err = "Workflow completed but no final video was found."
            update_job_status(job_id, "FAILED", 90, error_msg=err)
            return {"error": "Workflow failed. No final video was found in the ComfyUI output folder."}
                
        time.sleep(1)


if __name__ == '__main__':
    # Start ComfyUI in a separate thread
    server_thread = threading.Thread(target=start_comfyui)
    server_thread.daemon = True
    server_thread.start()

    # Wait for the server to be ready (will exit script if ComfyUI fails)
    check_server_ready(COMFYUI_URL)
    
    # Start the RunPod serverless worker
    runpod.serverless.start({'handler': handler})