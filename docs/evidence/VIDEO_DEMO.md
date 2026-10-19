# Video demo: stored c93 verification

[Watch the unlisted YouTube demo](https://youtu.be/16P-i_Akzgk).
This is a **90-second captioned screenshot walkthrough** of the app's stored
verification run `c93a2d6a99390dabc3eb3816834726a4`. Signed-out playback of the
complete video was checked on 2026-10-19.

The video presents existing execution evidence. It does not record a fresh
free-text goal investigation, model-generated plan or new dispatch. Live goal
planning and action claims require their own GoalRun records and independent
audits; this video is not that proof.

The stored matrix contains **six passed checks, two failed checks and zero
skips**. Its independently verified outcome is **blocked**, not a code pass or
completed repair. The declared environments are Python `redis` client versions
8.0.0 and 8.1.0. [GitHub artifact/JUnit proof](release-c93-independent-proof.json)
and [native graph/provider read-back proof](release-c93-cloud-proof.json) retain
the execution and delivery checks separately from the video's presentation.

## Public read-only references

- [App](https://baton-workspace.vercel.app/).
- [Stored execution](https://baton-workspace.vercel.app/api/public/release-runs/c93a2d6a99390dabc3eb3816834726a4).
- [Stored sealed plan](https://baton-workspace.vercel.app/api/public/release-plans/358043b754c6e408b3ac9c1e7cfebfb9).
- [Raw execution report](https://baton-workspace.vercel.app/api/public/release-runs/c93a2d6a99390dabc3eb3816834726a4/evidence).

## Local export provenance

The final local export was
`output/playwright/baton-production-c93-walkthrough-90s.webm`:

- Size: **3,852,984 bytes**.
- SHA-256: `f702fe208d625590bb854df803c6e5aad0a18312dfeeb636ec0cce751a138e31`.

The digest identifies the local WebM export; YouTube's transcoded playback has
different bytes. Video binaries, screenshots and private channel/account data
are not included in the source repository by this documentation change.
