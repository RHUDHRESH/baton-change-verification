# GitHub reuse register

**Full-build update:** the FalkorDB client (1.8.0) and official MCP SDK (2.3.0) are now installed, along with the supplied MIT-attributed benchmark world and adapted extraction/evaluation code. The table below records the original phase-one selection; current exact dependency pins are in `deploy/requirements.txt`. Source notices remain in adapted Python headers and `third_party/amb/LICENSE`, which is also included in the wheel. No competitor project was copied.

Checked against upstream GitHub pages on 2026-10-18. Reuse means using licensed libraries or retaining notices with adapted code. Future-phase entries below are selections for the architecture, not installed dependencies or completed integrations.

| Source | License checked | Intended use | State |
|---|---|---|---|
| [FalkorDB Python client](https://github.com/FalkorDB/falkordb-py) | [MIT, FalkorDB 2023](https://github.com/FalkorDB/falkordb-py/blob/main/LICENSE) | M02 database client rather than writing a protocol layer | Selected; not installed |
| [agent-memory-bench](https://github.com/zhang-liz/agent-memory-bench) | [MIT, Liz Zhang 2026](https://github.com/zhang-liz/agent-memory-bench/blob/main/LICENSE) | M05 structured extraction/cache and fake-model patterns; M07 fairness and cluster-bootstrap method | Inspected upstream README/license; adaptation deferred |
| [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | [MIT, Anthropic PBC 2024](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) | M08 typed MCP transport and tools | Selected; not installed |
| [FalkorDB engine v4.22.1](https://github.com/FalkorDB/FalkorDB/releases/tag/v4.22.1) | Pack reports SSPL; engine license not independently audited in this phase | M02 graph service matching supplied query contracts | Release existence checked; no engine run |

For actual code adaptation, record the full upstream commit and source paths, preserve the complete MIT notice, and keep a small reviewed diff. The pack mentions abbreviated benchmark commit `b8ccc40`; it has not been resolved and no current upstream code was copied into the runtime. Upstream benchmark defaults currently mention FalkorDB 6.0.1, while this pack targets 4.22.1: benchmark setup commands must not override Baton's selected engine.

Phase one needs only Python's standard library. Its substantive implementation is reused from the **user-supplied pack**, with provenance in INPUT_PROVENANCE.md. Adding unrelated GitHub code to the generator would add dependencies without improving the required behavior.

The pack's `third_party/amb/` already contains vendored source and a license. It remains in the preserved reference snapshot and is excluded from the installed project package. No competitor hackathon project was used. Future FastAPI, UI and deployment dependencies remain deferred, including final version/license verification at the phase where they are added.
