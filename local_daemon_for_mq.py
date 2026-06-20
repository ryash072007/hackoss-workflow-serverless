import time
import json
import psycopg2
import requests
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()
# --- Configuration ---
DB_DSN = os.environ.get("PG_DSN")
QUEUE_NAME = os.environ.get("PGMQ_QUEUE_NAME")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.environ.get("ppow5bwr1w4nrr")

# RunPod synchronous execution endpoint
RUNPOD_URL = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"

def get_db_connection():
    """Establish a connection to Postgres."""
    return psycopg2.connect(DB_DSN)

def process_queue():
    print(f"Starting PGMQ Dispatcher. Polling queue: {QUEUE_NAME}...")
    
    # Establish connection outside the loop, but check health inside
    conn = get_db_connection()
    conn.autocommit = True
    
    while True:
        try:
            # Ensure connection is alive
            if conn.closed != 0:
                print("Reconnecting to database...")
                conn = get_db_connection()
                conn.autocommit = True

            with conn.cursor() as cur:
                # 1. Read message with a Visibility Timeout (vt) of 300 seconds
                # This matches your RunPod 5-minute timeout. If RunPod fails and we don't delete
                # the message, it returns to the queue after 300 seconds.
                cur.execute(f"SELECT * FROM pgmq.read('{QUEUE_NAME}', 300, 1);")
                message = cur.fetchone()

                if not message:
                    # No message found, wait and poll again
                    time.sleep(3)
                    continue

                # PGMQ read returns: (msg_id, read_ct, enqueued_at, vt, message_payload)
                msg_id = message[0]
                payload = message[4]  # The JSONB payload
                
                print(f"Message {msg_id} acquired. Payload: {payload}")
                
                # 2. Extract data and trigger RunPod
                video_url = payload.get("video_url")
                
                if not video_url:
                    print(f"Error: No video_url in message {msg_id}. Archiving invalid message.")
                    cur.execute(f"SELECT * FROM pgmq.archive('{QUEUE_NAME}', %s);", (msg_id,))
                    continue

                runpod_payload = {
                    "input": {
                        "video_url": video_url
                    }
                }
                
                headers = {
                    "Authorization": f"Bearer {RUNPOD_API_KEY}",
                    "Content-Type": "application/json"
                }

                print(f"Triggering RunPod execution for message {msg_id}...")
                response = requests.post(
                    RUNPOD_URL, 
                    json=runpod_payload, 
                    headers=headers,
                    timeout=310 # Slightly higher than the 300s RunPod max timeout
                )
                
                # 3. Handle Response and Queue state
                if response.status_code == 200:
                    runpod_result = response.json()
                    status = runpod_result.get("status")
                    
                    if status == "COMPLETED":
                        output = runpod_result.get("output", {})
                        if "error" in output:
                            print(f"RunPod execution logic failed: {output['error']}")
                            # Depending on your retry logic, you might want to archive it or let it visibility-timeout
                            # Here we archive it to avoid poison-pill loops.
                            cur.execute(f"SELECT * FROM pgmq.archive('{QUEUE_NAME}', %s);", (msg_id,))
                        else:
                            print(f"Success! Output URL: {output.get('video_url')}")
                            # Complete message: delete from queue (or archive if you want to keep history)
                            cur.execute(f"SELECT * FROM pgmq.delete('{QUEUE_NAME}', %s);", (msg_id,))
                    else:
                        print(f"RunPod Job Failed or Timed Out. Status: {status}. RunPod Response: {runpod_result}")
                        # Do NOT delete message. Let the visibility timeout expire so it retries.
                else:
                    print(f"HTTP Error calling RunPod: {response.status_code} - {response.text}")
                    # Do NOT delete message. Let it retry.
                
        except psycopg2.Error as db_err:
            print(f"Database error: {db_err}")
            time.sleep(5) # Backoff before retrying db connection
        except requests.exceptions.RequestException as req_err:
            print(f"Network/RunPod error: {req_err}")
            time.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_queue()