# Source publication and execution boundary

The intended source-only public mirror is
[`RHUDHRESH/baton-change-verification`](https://github.com/RHUDHRESH/baton-change-verification).
Publication status and the reviewed commit must be established by the final
release record; preparing this document does not claim that publication occurred.

The mirror is to preserve genuine reviewed Git source history and byte-identical
runtime, worker, workflow and locked-check files. It must not construct artificial
prediction-first commits or rewrite an old evaluation assertion. The existing
documentation discloses that the supplied pack's historical results were already
known; commit-order checks do not establish blind preregistration.

Execution remains in the original private runner repository. Its Actions logs,
run metadata, secrets, settings and transient callback capabilities are not copied
by mirroring Git source. Actions must be disabled in the public source mirror,
and no provider credentials belong there. Public demo endpoints and declared
runner/destination identities in the reviewed source are intentional identifiers;
they are not provider credentials.

The application exposes independently verified public evidence and receipts for
each actual execution. A source commit, mirrored code, passing contract tests,
workflow dispatch or callback alone does not prove a passing release. Check the
per-environment evidence and graph/provider read-backs. Failed required checks
must remain a blocked outcome.

See [third-party notices](THIRD_PARTY_NOTICES.md) for source attributions and the
separate license boundaries retained in the mirror.
