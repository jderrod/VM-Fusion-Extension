"""
Serve the G-Code Cut Length Analyzer on the local network.

Run:
    python serve.py

Then anyone on your WiFi can access it at:
    http://<YOUR_IP>:8080

Each visitor gets their own independent instance (all processing is client-side).
Press Ctrl+C to stop.
"""

import http.server
import socketserver
import socket

PORT = 8080

def get_local_ip():
    """Get the machine's local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Suppress per-request log noise."""
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    local_ip = get_local_ip()

    with socketserver.TCPServer(("0.0.0.0", PORT), QuietHandler) as httpd:
        print(f"G-Code Cut Length Analyzer")
        print(f"{'='*40}")
        print(f"  Local:   http://localhost:{PORT}")
        print(f"  Network: http://{local_ip}:{PORT}")
        print(f"{'='*40}")
        print(f"Share the Network URL with anyone on your WiFi.")
        print(f"Each person gets their own independent session.")
        print(f"Press Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
