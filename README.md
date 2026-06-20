# ComfyUI Serverless Worker: Stickman Animation Pipeline

This repository contains a serverless backend worker designed for deployment on RunPod. It encapsulates a local ComfyUI instance, executes a predefined video-to-video animation workflow (`oss_stickman_api.json`), handles S3 object storage operations (download/upload), and pushes job state telemetry to a custom backend API.

ENDPOINT_ID: ppow5bwr1w4nrr

## Architecture Overview

1. **Initialization:** The worker spins up a local ComfyUI subprocess within the Docker container.
2. **Payload Reception:** Accepts a JSON payload containing an input `objectKey` referencing a file in the configured S3 bucket.
3. **Execution:** Downloads the target video from S3, injects it into the ComfyUI workflow, and queues the generation prompt.
4. **Telemetry:** Continuously updates a custom backend API with the processing progress (percentage and status).
5. **Storage & Egress:** Uploads the generated MP4 directly to the designated S3 output bucket via `boto3` and pushes the final object key to the custom backend API. The RunPod endpoint returns a simple success state.

## Environment Variables (`.env`)

The container requires the following environment variables for S3 authentication and backend telemetry.

```env
# S3 Configuration (Supabase/R2/AWS)
SUPABASE_S3_ENDPOINT=https://<YOUR_S3_ENDPOINT>
SUPABASE_S3_ACCESS_KEY=<YOUR_ACCESS_KEY>
SUPABASE_S3_SECRET_KEY=<YOUR_SECRET_KEY>
SUPABASE_S3_REGION=auto
SUPABASE_S3_BUCKET=<YOUR_INPUT_BUCKET_NAME>
SUPABASE_S3_BUCKET_OUTPUT=<YOUR_OUTPUT_BUCKET_NAME>

# Backend Telemetry Configuration
BACKEND_API_URL=https://<YOUR_BACKEND_API>
BACKEND_API_KEY=<YOUR_BEARER_TOKEN>
X_ADMIN_TOKEN=<YOUR_ADMIN_TOKEN>

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
  -d '{"input": {"objectKey": "test_video.mp4"}}'

```

## Production API Integration

In a production environment, the generation process exceeds standard HTTP timeout thresholds. Utilize the asynchronous `/run` endpoint. Do not use `/runsync` in production.

### 1. Dispatch Request

Send the initial payload to the RunPod endpoint. The input requires the S3 `objectKey` of the source video.

```http
POST [https://api.runpod.ai/v2/](https://api.runpod.ai/v2/)<ENDPOINT_ID>/run
Authorization: Bearer <RUNPOD_API_KEY>
Content-Type: application/json

{
  "input": {
    "objectKey": "user_uploads/source_video.mp4"
  }
}

```

**Response:** Returns a `job_id` and a status of `IN_QUEUE`.

### 2. Status Polling & Backend Telemetry

The worker uses dual-reporting.

**RunPod Native Polling:**
Check the execution state via the RunPod API.

```http
GET [https://api.runpod.ai/v2/](https://api.runpod.ai/v2/)<ENDPOINT_ID>/status/<JOB_ID>
Authorization: Bearer <RUNPOD_API_KEY>

```

**Backend Webhook (Push):**
Simultaneously, the worker issues `PUT` requests to your configured `BACKEND_API_URL` to update granular job states:

* 5%: Initializing S3
* 15%: Download complete
* 20%: Prompt queued
* 90%: Workflow execution finished
* 100%: Upload complete

### 3. Final Output

Upon completion, the script uploads the resulting MP4 using the `job_id` as the filename (`<job_id>.mp4`). The backend telemetry will receive the `stickmanifiedS3ObjectKey`.

The RunPod status endpoint will return a standard completion object without generating a pre-signed URL:

```json
{
  "status": "COMPLETED",
  "output": {
    "status": "success"
  }
}

```

Force Update: 1
