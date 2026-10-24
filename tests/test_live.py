import sys, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "web"))
import server

class LiveClusterTest(unittest.TestCase):
    def test_real_services_localize_injected_latency(self):
        ThreadingHTTPServer.request_queue_size = 256
        srv = ThreadingHTTPServer(("127.0.0.1", 8080), server.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
        live = server.LIVE
        try:
            live.start(25); time.sleep(14)
            live.inject("payment", "latency"); time.sleep(14)
            r = live.snapshot()
        finally:
            live.stop(); srv.shutdown(); srv.server_close()
        self.assertIn("checkout->payment", r["graph"])
        self.assertEqual(r["ranking"][0]["suspected_component"], "payment")

if __name__ == "__main__": unittest.main()
