import sys, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "web"))
import server

class LiveClusterTest(unittest.TestCase):
    """Boots nine real service processes per fault, breaks `payment`, and checks the diagnosis and report.

    Latency and process-down must rank `payment` first. Errors and retry storms are partly masked by caller
    retries, so on a noisy machine the test only requires `payment` in the top three."""
    @classmethod
    def setUpClass(cls):
        ThreadingHTTPServer.request_queue_size = 256
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 8080), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def run_fault(self, mode):
        live = server.LIVE
        try:
            live.start(25); time.sleep(14)
            live.inject("payment", mode); time.sleep(14)
            return live.snapshot(), live.incident_report()
        finally:
            live.stop()

    def test_each_fault_is_localized_to_payment(self):
        for mode in ("latency", "errors", "retry-storm", "down"):
            with self.subTest(fault=mode):
                r, md = self.run_fault(mode)
                self.assertIn("checkout->payment", r["graph"])
                ranked = [x["suspected_component"] for x in r["ranking"]]
                self.assertIn("payment", ranked[:3])
                if mode in ("latency", "down"):   # strong signals must be exact; retried errors can be buried by noise
                    self.assertEqual(ranked[0], "payment")
                self.assertIsNotNone(r["live"]["detected_at_s"])
                self.assertIn("**Suspected root cause:** `payment`", md)
                self.assertIn(f"`{mode}` into `payment`", md)

if __name__ == "__main__": unittest.main()
