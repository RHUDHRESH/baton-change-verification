These artifacts were produced on 2026-10-19 by release_gate_worker.run_plan.
Each environment used a new disposable FalkorDB container, without published
ports or host mounts. Client Python 3.13.5 was pinned by a registry digest.
Every dependency wheel was installed with the checked-in --require-hashes lock.
The archive is the original pinned upstream source, used only as fixture data.

Python redis client 8.0.0: four passed.
Python redis client 8.1.0: two sync cases passed; two async cases failed with himport_registry.
These dependency versions do not identify the FalkorDB server. The disposable
server image is pinned separately in each artifact environment record.
The independent verifier must retain a verified blocked outcome, not a green
release or an infrastructure error. The test module mutates copies of this real
evidence to exercise rejection paths. The local workflow SHA is a placeholder;
production additionally authenticates GitHub jobs and artifact provenance.
