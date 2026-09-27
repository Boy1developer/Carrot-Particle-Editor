import json, threading, urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
with open("preview/last_effect.json", "w", encoding="utf-8") as f:
    json.dump({"version": "1.0", "type": "2d",
               "emitter": {"mode": "Infinite"}, "states": []}, f)
srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory="."))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
for path in ("preview/preview.html", "preview/preview.js", "preview/last_effect.json"):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/{path}") as r:
        body = r.read()
        assert len(body) > 20, path
        print(path, "OK", len(body), "bytes")
srv.shutdown()
print("SERVER OK")
