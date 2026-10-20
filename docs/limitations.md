# Where the diagnoser is wrong, and why

The deterministic score can mistake a **victim** for the root when an upstream caller retries aggressively: its edge may show errors earlier than a saturated dependency. Clock skew and batching can likewise invert failure ordering. The ranker currently observes only synchronous client spans; queues, caches, fan-out joins, and missing instrumentation create invisible edges and can understate the blast radius.

Percentiles are exact for the retained raw span sample, but they are not necessarily end-user latency: sampling, dropped spans, and client/server clock differences bias them. Proxy records should be used to cross-check counts, status, and timing. Prometheus histogram quantiles are bucket approximations and will not exactly equal raw p99; align labels and windows before interpreting a gap.

The included demo is a deterministic synthetic surrogate, not a claim of a completed live fault campaign. Before production use, run the Toxiproxy/Chaos Mesh matrix against a pinned OpenTelemetry Demo or Online Boutique version, retain the hidden fault schedule separately, compare the derived graph to the app's documented topology, and run a schema-specific adapter on a public labeled RCA benchmark. The analysis stays deterministic throughout; an LLM may summarize the final JSON only.
