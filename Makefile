.PHONY: live demo-fault synthetic-large test benchmark ui clean

demo-fault:
	PYTHONPATH=src python3 -m diag.cli demo --fault latency --out run

synthetic-large:
	PYTHONPATH=src python3 -m diag.cli generate-large --fault latency --out data/synthetic-large

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

benchmark:
	PYTHONPATH=src python3 -m diag.cli benchmark

live: ui

ui:
	PYTHONPATH=src python3 web/server.py

clean:
	rm -rf run
