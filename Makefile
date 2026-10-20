.PHONY: demo-fault test benchmark clean

demo-fault:
	PYTHONPATH=src python3 -m diag.cli demo --fault latency --out run

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

benchmark:
	PYTHONPATH=src python3 -m diag.cli benchmark

clean:
	rm -rf run
