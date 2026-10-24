"""Static wiring of the live demo: which service listens where and who it calls.

`calls` maps a downstream peer to the number of client-side retries the caller makes.
The diagnoser never reads this; it rediscovers the graph from emitted spans.
"""
BASE_PORT = 9100
SERVICES = {
    "frontend":   {"calls": {"catalog": 0, "checkout": 0}},
    "catalog":    {"calls": {"product-db": 0}},
    "product-db": {"calls": {}},
    "checkout":   {"calls": {"inventory": 0, "payment": 2, "shipping": 0}},
    "inventory":  {"calls": {}},
    "payment":    {"calls": {"fraud": 0, "ledger": 0}},
    "fraud":      {"calls": {}},
    "ledger":     {"calls": {}},
    "shipping":   {"calls": {}},
}
for i, name in enumerate(SERVICES):
    SERVICES[name]["port"] = BASE_PORT + i

def url_of(name: str) -> str:
    return f"http://127.0.0.1:{SERVICES[name]['port']}"
