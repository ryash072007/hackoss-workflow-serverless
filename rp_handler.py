import runpod
import subprocess
import threading
import time
import requests
import json
import uuid
import os
import boto3
from botocore.config import Config
from urllib.parse import urlparse

# ComfyUI server setup
COMFYUI_DIR = "/ComfyUI"
COMFYUI_URL = "http://127.0.0.1:8188"

def start_comfyui():
    """Starts the ComfyUI server."""
    command = "python3 main.py --listen"
    # Execute the subprocess in COMFYUI_DIR without changing the global process directory
    server_process = subprocess.Popen(command.split(), cwd=COMFYUI_DIR)
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

    headers = {
        "Content-Type": "application/json"
    }
    
    # If your backend requires an auth token to prevent random people from updating jobs
    if BACKEND_API_KEY:
        headers["Authorization"] = f"Bearer {BACKEND_API_KEY}"

    try:
        response = requests.put(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"Successfully updated backend job {job_id} to {status}")
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL: Failed to update backend job status for {job_id}. Error: {str(e)}")

def handler(event):
    """The serverless handler function."""
    print("Worker Start")
    
    # Capture the unique RunPod job ID to use as the output filename
    job_id = event.get('id', str(uuid.uuid4())) 
    
    input_data = event.get('input', {})
    object_key = input_data.get('objectKey')

    if not object_key:
        err = "objectKey not provided in input payload"
        update_job_status(job_id, "FAILED", 0, error_msg=err)
        return {"error": "object_key not provided"}

    update_job_status(job_id, "IN_PROGRESS", 5)
    bucket_name = os.environ.get('SUPABASE_S3_BUCKET')
    
    # Initialize S3 Client immediately for both download and upload
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

    # Download source video using objectKey
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

    # Load the workflow using an absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workflow_path = os.path.join(script_dir, "oss_stickman_api.json")
    
    with open(workflow_path, 'r') as f:
        prompt = json.load(f)

    # Update the video path in the workflow
    # Node 154 is the LoadVideo node
    prompt["154"]["inputs"]["video"] = video_filename

    # Queue the prompt
    prompt_id = queue_prompt(prompt)['prompt_id']
    
    update_job_status(job_id, "IN_PROGRESS", 20)

    # Wait for the output
    while True:
        history = get_history(prompt_id)
        
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
                        bucket_name = os.environ.get('SUPABASE_S3_BUCKET_OUTPUT') # BUCKET_NAME
                        
                        # Upload directly to R2
                        s3_client.upload_file(physical_path, bucket_name, upload_filename, ExtraArgs={'ContentType': 'video/mp4'})
                        
                        # Generate SigV4 pre-signed URL
                        # public_url = s3_client.generate_presigned_url(
                        #     'get_object',
                        #     Params={'Bucket': bucket_name, 'Key': upload_filename},
                        #     ExpiresIn=604800 
                        # )
                        
                        # Clean up the local file to prevent storage bloat
                        os.remove(physical_path)
                        if os.path.exists(input_video_path):
                            os.remove(input_video_path)
                        
                        update_job_status(job_id, "COMPLETED", 100, object_key=upload_filename)

                        return {
                            "status": "success", 
                            # "video_url": public_url
                        }
            
            err = "Workflow completed but no final video was found."
            update_job_status(job_id, "FAILED", 90, error_msg=err)
            return {"error": "Workflow failed. No final video was found in the ComfyUI output folder."}
                
        time.sleep(1)


if __name__ == '__main__':
    # Start ComfyUI in a separate thread
    server_thread = threading.Thread(target=start_comfyui)
    server_thread.daemon = True
    server_thread.start()

    # Wait for the server to be ready
    check_server_ready(COMFYUI_URL)
    
    # Start the RunPod serverless worker
    runpod.serverless.start({'handler': handler})