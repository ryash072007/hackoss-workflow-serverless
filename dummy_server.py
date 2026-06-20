from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class RequestLogger(BaseHTTPRequestHandler):
    def _log_request(self):
        print("\n" + "="*50)
        print(f"📥 INCOMING {self.command} REQUEST")
        print("="*50)
        print(f"Path: {self.path}")
        print("-" * 50)
        print(f"Headers:\n{self.headers}")
        
        # Check if there is a payload body
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            post_data = self.rfile.read(content_length).decode('utf-8')
            print("-" * 50)
            print("Payload (Body):")
            
            # Try to format as pretty JSON if possible, otherwise print raw string
            try:
                parsed_json = json.loads(post_data)
                print(json.dumps(parsed_json, indent=2))
            except json.JSONDecodeError:
                print(post_data)
        else:
            print("Payload (Body): <Empty>")
            
        print("="*50 + "\n")

        # Always return a 200 OK success status
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "success", "message": "Payload received by dummy server"}')

    # Route all HTTP methods to the same logging function
    def do_GET(self): self._log_request()
    def do_POST(self): self._log_request()
    def do_PUT(self): self._log_request()
    def do_PATCH(self): self._log_request()
    def do_DELETE(self): self._log_request()

    # Suppress the default HTTP server logging to keep the console clean
    def log_message(self, format, *args):
        pass

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestLogger)
    print(f"🚀 Dummy server listening on port {port}...")
    print(f"Send requests to http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server.")
        httpd.server_close()

if __name__ == '__main__':
    run()