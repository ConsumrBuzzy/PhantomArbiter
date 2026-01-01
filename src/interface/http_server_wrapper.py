
import os
import http.server
import socketserver
import threading
from src.shared.system.logging import Logger

class HttpServerWrapper:
    """
    "The Portal" - Threaded HTTP Server
    Serves the static frontend/dashboard.html to the user.
    """

    def __init__(self, port: int = 8000, directory: str = "frontend"):
        self.port = port
        self.directory = directory
        self.thread = None
        self.httpd = None

    def start(self):
        """Start the HTTP server in a daemon thread."""
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        Logger.info(f"   🌀 The Void Portal open at http://localhost:{self.port}/dashboard.html")

    def _run_server(self):
        """Internal server loop."""
        # Change directory to serve files correctly
        os.chdir(os.path.abspath(os.path.join(os.getcwd(), ".")))
        
        # Custom handler to map / to dashboard.html if needed, or just serve dir
        Handler = http.server.SimpleHTTPRequestHandler
        
        # Allow reusing address to prevent "Address already in use" errors during quick restarts
        socketserver.TCPServer.allow_reuse_address = True
        
        with socketserver.TCPServer(("", self.port), Handler) as httpd:
            self.httpd = httpd
            # Serve until shutdown (thread killed)
            httpd.serve_forever()
            
if __name__ == "__main__":
    server = HttpServerWrapper()
    server.start()
    input("Press Enter to stop...")
