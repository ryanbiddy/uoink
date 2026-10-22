"""Child fixture serving the product HTTP Handler on an isolated loopback port."""
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
assert os.environ.get("UOINK_ISOLATED_PROFILE")
assert os.environ.get("UOINK_ISOLATED_APP_DIR")
assert os.environ.get("UOINK_ISOLATED_PORT") not in (None, "5179")

import server
from tests.mcp_wire import HttpClient

server.TOKEN = HttpClient.TOKEN
with server._YoinkHTTPServer(("127.0.0.1", server.PORT), server.Handler) as httpd:
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    print(json.dumps({"jsonrpc": "2.0", "method": "fixture/ready",
                      "params": {"port": httpd.server_port}}), flush=True)
    try:
        sys.stdin.read()  # EOF gives the parent a clean shutdown path.
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
