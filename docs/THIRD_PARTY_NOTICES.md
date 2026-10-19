# Third-party material and license boundaries

Original project-code licensing is unspecified. No blanket open-source license
or new license grant for another author's code is asserted here.

| Included material | Attribution and notice |
| --- | --- |
| `third_party/amb/world.py` and attributed benchmark/extraction/evaluation adaptations | agent-memory-bench, Liz Zhang, copyright 2026, MIT. Source headers and the complete notice remain in `third_party/amb/LICENSE`. |
| `web/vendor/cytoscape/` | Cytoscape.js 3.34.4, The Cytoscape Consortium, copyright 2016–2026, MIT. Original LICENSE and source/hash provenance remain beside the vendored file. |
| `fixtures/release_py211/public_sources.json` source/documentation excerpts | FalkorDB/falkordb-py at commit `207000da70ca183ab02990a98bdd97d0a3e3bb1b`, copyright 2023 FalkorDB, MIT. The full pinned notice is in `fixtures/release_py211/LICENSE`. Public issue/review authorship remains in the captured author fields. |
| `tests/fixtures/release_verifier/artifact/source.zip` | Original public archive of the same pinned Python-client source, including its upstream MIT LICENSE. This is a test artifact, not the user's build-pack ZIP. |
| `docs/evidence/kan2-fixtures/` upstream-derived Rust patch material | Pinned FalkorDB/FalkorDB source attribution and modification descriptions remain in that fixture's README. The complete unmodified upstream LICENSE is retained as `SSPL-1.0.txt`; it includes Server Side Public License and Elastic License text as shipped upstream. That material is not relicensed as MIT. |
| Supplied Baton base snapshot and reference checker/generator material | Credited to the user-supplied snapshot identified in its metadata as `980c2e2`; provenance is documented in `INPUT_PROVENANCE.md`. That identifier is source metadata rather than an independently authenticated upstream checkout. Existing source notices remain intact. |

Python packages and container images are installed dependencies rather than
vendored dependency binaries in this repository. Their respective upstream
licenses continue to apply. The notices above identify included source material;
they do not establish one license for the entire project.
