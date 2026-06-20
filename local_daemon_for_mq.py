import time
import json
import psycopg2
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
DB_DSN = os.environ.get("PG_DSN")
QUEUE_NAME = os.environ.get("PGMQ_QUEUE_NAME")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")

# Correction: Search for the variable name, fallback to the literal string
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "ppow5bwr1w4nrr")
RUNPOD_URL = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"
# RUNPOD_URL = f"https://localhost:8000/runsync"

def get_db_connection():
    """Establish a connection to Postgres."""
    if not DB_DSN:
        raise ValueError("PG_DSN is missing.")
    return psycopg2.connect(DB_DSN)

def process_queue():
    print(f"Starting PGMQ Dispatcher. Polling queue: {QUEUE_NAME}...")
    
    conn = get_db_connection()
    conn.autocommit = True
    
    while True:
        try:
            if conn.closed != 0:
                print("Reconnecting to database...")
                conn = get_db_connection()
                conn.autocommit = True

            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM pgmq.read('{QUEUE_NAME}', 300, 1);")
                message = cur.fetchone()

                if not message:
                    time.sleep(3)
                    continue

                msg_id = message[0]
                payload = message[4]
                
                print(f"Message {msg_id} acquired. Payload: {payload}")
                
                # Extract new payload schema
                object_key = payload.get("objectKey")
                job_id = payload.get("jobId")
                
                if not object_key:
                    print(f"Error: No objectKey in message {msg_id}. Archiving invalid message.")
                    cur.execute(f"SELECT * FROM pgmq.archive('{QUEUE_NAME}', %s);", (msg_id,))
                    continue

                # Forward objectKey to RunPod
                runpod_payload = {
                    "input": {
                        "objectKey": object_key,
                        "jobId": job_id
                    }
                }
                
                headers = {
                    "Authorization": f"Bearer {RUNPOD_API_KEY}",
                    "Content-Type": "application/json"
                }

                print(f"Triggering RunPod execution for job {job_id}...")
                response = requests.post(
                    RUNPOD_URL, 
                    json=runpod_payload, 
                    headers=headers,
                    timeout=310
                )
                
                if response.status_code == 200:
                    runpod_result = response.json()
                    status = runpod_result.get("status")
                    
                    if status == "COMPLETED":
                        output = runpod_result.get("output", {})
                        if "error" in output:
                            print(f"RunPod execution failed: {output['error']}")
                            cur.execute(f"SELECT * FROM pgmq.archive('{QUEUE_NAME}', %s);", (msg_id,))
                        else:
                            print(f"Success!")
                            cur.execute(f"SELECT * FROM pgmq.delete('{QUEUE_NAME}', %s);", (msg_id,))
                    else:
                        print(f"RunPod Job Failed or Timed Out. Status: {status}. RunPod Response: {runpod_result}")
                else:
                    print(f"HTTP Error calling RunPod: {response.status_code} - {response.text}")
                
        except psycopg2.Error as db_err:
            print(f"Database error: {db_err}")
            time.sleep(5)
        except requests.exceptions.RequestException as req_err:
            print(f"Network error: {req_err}")
            time.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_queue()