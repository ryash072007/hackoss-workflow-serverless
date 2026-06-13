# ComfyUI Serverless Worker: Stickman Animation Pipeline

This repository contains a serverless backend worker designed for deployment on RunPod. It encapsulates a ComfyUI instance, executes a predefined video-to-video animation workflow (`oss_stickman_api.json`), and handles direct cloud storage uploads to Cloudflare R2 using standard S3 APIs.

## Architecture Overview

1. **Initialization:** The worker spins up a local ComfyUI subprocess within the Docker container.
2. **Payload Reception:** Accepts a JSON payload containing an input `video_url`.
3. **Execution:** Injects the downloaded video into the ComfyUI workflow and queues the generation prompt.
4. **Storage & Egress:** Bypasses local network transfer by locating the generated MP4 directly on the container's disk, uploading it to Cloudflare R2 via `boto3`, and generating a pre-signed download URL valid for 7 days.

## Prerequisites

* **Docker:** For local testing and container compilation.
* **RunPod Account:** For serverless endpoint deployment.
* **Cloudflare R2 Bucket:** For zero-egress object storage.

## Environment Variables (`.env`)

For local execution and production deployment, the container requires the following environment variables to authenticate with Cloudflare R2.

Create a `.env` file in the root directory:

```env
BUCKET_ENDPOINT_URL=https://<YOUR_CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com
BUCKET_NAME=<YOUR_BUCKET_NAME>
AWS_DEFAULT_REGION=auto
BUCKET_ACCESS_KEY_ID=<YOUR_R2_ACCESS_KEY>
BUCKET_SECRET_ACCESS_KEY=<YOUR_R2_SECRET_KEY>

```

*Note: Ensure `.env` is added to your `.gitignore` file to prevent credential leakage.*

## Local Testing (Docker)

To test the worker locally, utilize bind mounts to inject the handler script, workflow JSON, and environment variables into the base container runtime.

```bash
docker run -it --rm --gpus all -p 8000:8000 \
  --env-file .env \
  -v "$PWD/rp_handler.py:/rp_handler.py" \
  -v "$PWD/oss_stickman_api.json:/oss_stickman_api.json" \
  comfy-hackoss-worker python3 -u /rp_handler.py --rp_serve_api --rp_api_host 0.0.0.0

```

Once the terminal outputs `ComfyUI server is ready.`, dispatch a synchronous test payload to the local endpoint:

```bash
curl -X POST http://localhost:8000/runsync \
  -H "Content-Type: application/json" \
  -d '{"input": {"video_url": "https://example.com/path/to/input.mp4"}}'

```

## Production API Integration

In a production environment, the generation process (approx. 130 seconds) exceeds standard HTTP timeout thresholds. **You must utilize the asynchronous `/run` endpoint.** Do not use `/runsync` in production.

### 1. Dispatch Request

Send the initial payload to the RunPod endpoint.

```http
POST https://api.runpod.ai/v2/<ENDPOINT_ID>/run
Authorization: Bearer <RUNPOD_API_KEY>
Content-Type: application/json

{
  "input": {
    "video_url": "https://example.com/path/to/input.mp4"
  }
}

```

**Response:** Returns a `job_id` and a status of `IN_QUEUE`.

### 2. Status Polling

Implement a client-side polling loop (every 3–5 seconds) to check the job status.

```http
GET https://api.runpod.ai/v2/<ENDPOINT_ID>/status/<JOB_ID>
Authorization: Bearer <RUNPOD_API_KEY>

```

### 3. Final Output

Once the worker completes the generation and S3 upload, the status endpoint will return `COMPLETED` along with the pre-signed R2 URL.

```json
{
  "status": "COMPLETED",
  "output": {
    "status": "success",
    "video_url": "https://<R2_PRESIGNED_URL_PARAMETERS>"
  }
}

```