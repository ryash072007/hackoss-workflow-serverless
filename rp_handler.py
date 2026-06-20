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

def handler(event):
    """The serverless handler function."""
    print("Worker Start")
    
    # Capture the unique RunPod job ID to use as the output filename
    job_id = event.get('id', str(uuid.uuid4())) 
    
    input_data = event.get('input', {})
    video_url = input_data.get('video_url')

    if not video_url:
        return {"error": "video_url not provided"}

    # Download the input video
    video_filename = os.path.basename(urlparse(video_url).path)
    input_video_path = os.path.join(COMFYUI_DIR, "input", video_filename)
    download_video(video_url, input_video_path)

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
    
    # Wait for the output
    while True:
        history = get_history(prompt_id)
        
        if prompt_id in history:
            outputs = history[prompt_id].get('outputs', {})
            
            for node_output in outputs.values():
                media_list = node_output.get('gifs') or node_output.get('videos')
                
                if media_list and media_list[0].get('type') == 'output':
                    filename = media_list[0]['filename']
                    physical_path = os.path.join(COMFYUI_DIR, "output", filename)
                    
                    if os.path.exists(physical_path):
                        print(f"Success. Video located at: {physical_path}")
                        
                        upload_filename = f"{job_id}.mp4"
                        bucket_name = os.environ.get('SUPABASE_S3_BUCKET') # BUCKET_NAME
                        
                        # Standard Boto3 initialization for Cloudflare R2
                        s3_client = boto3.client(
                            's3',
                            endpoint_url=os.environ.get('SUPABASE_S3_ENDPOINT'), # BUCKET_ENDPOINT_URL
                            aws_access_key_id=os.environ.get('SUPABASE_S3_ACCESS_KEY'), # BUCKET_ACCESS_KEY_ID
                            aws_secret_access_key=os.environ.get('SUPABASE_S3_SECRET_KEY'), # BUCKET_SECRET_ACCESS_KEY
                            region_name=os.environ.get('SUPABASE_S3_REGION', 'auto') # AWS_DEFAULT_REGION
                        )
                        
                        # Upload directly to R2
                        s3_client.upload_file(physical_path, bucket_name, upload_filename, ExtraArgs={'ContentType': 'video/mp4'})
                        
                        # Generate SigV4 pre-signed URL
                        public_url = s3_client.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': bucket_name, 'Key': upload_filename},
                            ExpiresIn=604800 
                        )
                        
                        # Clean up the local file to prevent storage bloat
                        os.remove(physical_path)
                        if os.path.exists(input_video_path):
                            os.remove(input_video_path)
                        
                        return {
                            "status": "success", 
                            "video_url": public_url
                        }
            
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