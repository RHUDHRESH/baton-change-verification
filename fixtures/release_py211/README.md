# Public Python-client source fixture

`public_sources.json` is a captured test fixture containing ten official GitHub
API responses for FalkorDB/falkordb-py issue #211, merged PR #212, public review
comments, and seven source/documentation files. Code and documentation are pinned
to commit `207000da70ca183ab02990a98bdd97d0a3e3bb1b`. Each record retains its public
URL, original response SHA-256, canonical payload hash, capture time, and public
author fields. Source records additionally retain content hashes and the commit.

The client code is copyright (c) 2023 FalkorDB, MIT. The complete, unchanged notice
from that pinned upstream commit is included as [LICENSE](LICENSE). Public issue
and review text remains attributed to the public author fields; the fixture does
not claim new authorship of that material or infer employment/code ownership.

Tests explicitly load this fixture to check source extraction and real FalkorDB
traversal. Production source capture fetches the approved GitHub API paths and
stores its own immutable captured versions. Cloud or provider failure never
causes production code to load this test fixture.

The separate `tests/fixtures/release_verifier/artifact/source.zip` is the original
public upstream source archive for this same pinned commit, including its
upstream LICENSE. It is not the user's supplied build-pack archive.
