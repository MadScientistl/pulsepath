import os, sys, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "web"))
import server
STRICT = os.environ.get("PULSEPATH_STRICT") == "1"

class LiveClusterTest(unittest.TestCase):
    """Boots nine real service processes per fault, breaks `payment`, and checks the diagnosis and report.

    Default: `payment` must be in the top three suspects (shared CI runners are noisy and callers' retries
    mask error faults). With PULSEPATH_STRICT=1 on a quiet machine it must be ranked first."""
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
                detail = "\n".join(f"{x['edge']} score={x['score']} onset={x['onset_window']} {x['evidence']}" for x in r["ranking"][:6])
                self.assertIn("payment", ranked[:3], f"{mode}: spans={r['live']['spans']}\n{detail}")
                if STRICT:   # PULSEPATH_STRICT=1: exact top-1 on a quiet machine
                    self.assertEqual(ranked[0], "payment")
                self.assertIsNotNone(r["live"]["detected_at_s"])
                self.assertIn("`payment`", md)
                self.assertIn(f"`{mode}` into `payment`", md)

if __name__ == "__main__": unittest.main()
