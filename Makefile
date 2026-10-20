.PHONY: demo-fault test benchmark ui clean

demo-fault:
	PYTHONPATH=src python3 -m diag.cli demo --fault latency --out run

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

benchmark:
	PYTHONPATH=src python3 -m diag.cli benchmark

ui:
	python3 -m http.server 8080

clean:
	rm -rf run
