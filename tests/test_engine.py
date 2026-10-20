import unittest
from diag.simulator import generate
from diag.ingest import load_spans
from diag.engine import report, percentile, burn_alert

class DiagnosticsTest(unittest.TestCase):
 def test_percentile(self): self.assertEqual(percentile([1,2,3,4,5],.95),4)
 def test_burn(self): self.assertTrue(burn_alert([.2]*60))
 def test_known_fault_ranks_payment(self):
  generate("errors","/tmp/diag-test",seed=5)
  r=report(load_spans("/tmp/diag-test/spans.json"))
  self.assertEqual(r["ranking"][0]["suspected_component"],"payment")
  self.assertIn("checkout->payment",r["graph"])
 def test_latency_fault_ranks_payment(self):
  generate("latency","/tmp/diag-latency",seed=5)
  r=report(load_spans("/tmp/diag-latency/spans.json"))
  self.assertEqual(r["ranking"][0]["suspected_component"],"payment")

if __name__ == "__main__": unittest.main()
