# Validation record

## Current compatibility check — November 3, 2026

Plugin 0.1.1 was tested on macOS arm64 through real Hermes discovery and
`model_tools.handle_function_call` dispatch using the existing PM-managed runtime:

* Hermes commit `6112c2adb9e11f69734a29be9d2696f345ffa06a`, reporting `0.22.6+404`.
* Published DeadBolt **2.0.1** native executable, SHA-256
  `a1c2942f5b5c2fad57dba6534633f52602dc2fbaae5f327a7456f1348143a688`.
* Python **3.14.9**. No environment installation, model call or owner profile change.

All 16 framework/process scenarios listed below and all four unit tests passed.
The actual framework's catalog validator also passed all 15 checks with no
warnings, using subprocess-isolated registration and no dependency installation.
The [dated machine-readable receipt](acceptance-macos-20261103.json) records actual
runtime versions; the test no longer hardcodes the Hermes release name. The
installed Hermes checkout had pre-existing changes to five JavaScript/package
manifests; those were not edited or exercised by this Python dispatch test.
The receipt's Git revision identifies its committed source baseline, not a claim
of a clean installed checkout.

CI now pins that Hermes revision and official DeadBolt 2.0.1 source
`e87519f700be03c27a564ed274907649224d256f`. A configured job is not a passing result.
Linux and clean-checkout CI outcomes remain separate from this Mac result.

This test uses a trusted private host and an operator-started sidecar. Loopback
restriction is not peer authentication or OS isolation. See README's access
disclosure. No model-mediated or whole-agent protection claim follows from these
checks.

## Historical initial acceptance — DeadBolt 2.0.0

The original local acceptance on macOS arm64 used:

* Hermes v0.22.2, commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`.
* DeadBolt 2.0.0 official installed executable, SHA-256
  `741f7f60966b56c7ce1f3d2268778c6bdb69f0ece23c6992980dc3708d134fd1`.
* Python 3.14.7 from Hermes's official PM workflow and lockfile.

The test loads the installed plugin copy through real Hermes discovery and calls
the tools through `model_tools.handle_function_call`. It runs a real local
DeadBolt sidecar, issues synthetic scoped credentials through its operator CLI,
approves fictional review data and independently inspects filesystem effects.
It does not substitute a fake DeadBolt decision or replace Hermes runtime code.

All 16 framework/process scenarios passed:

1. Preparation creates no output file; private review file is mode 0600.
2. Unapproved request is denied.
3. Path changed after approval is denied.
4. Content changed after approval is denied.
5. Exact reviewed content is written to the reviewed destination.
6. Reusing the consumed grant is denied.
7. Sidecar outage denies without writing.
8. Explicit operator restart preserves an unconsumed pending grant.
9. Missing profile-scoped admission secret denies.
10. Invalid admission credential denies.
11. Concurrent commit attempts complete exactly one write.
12. Expired exact action denies.
13. An existing file is preserved; admitted filesystem failure is reported as an
    unknown outcome rather than a safe-to-retry denial.
14. Symlinked parent refuses the write and creates nothing outside the workspace.
15. Killing the run blocks an already approved request.
16. `ensure` does not resurrect the killed identity.

The four unit tests independently cover invalid/escaping path forms, exclusive
UTF-8 creation/private permissions, symlink parents/destinations, and invalid
configuration/extra arguments. The catalog validator passed its manifest,
configuration, isolated registration, declared tools/hooks/middleware, collision,
dependency, security-scan and no-core-override checks.

[Original machine-readable macOS receipt](acceptance-macos.json), retained as
version-specific history. Current CI pins are stated above; consult the actual
run for the submitted commit.

## What this does not establish

No paid model call, model-mediated conversation, Desktop interaction, Windows
support, independent external review, whole-agent containment or Hermes
maintainer approval is claimed. The plugin's normal approval UI/secret form is
provided by Hermes; this acceptance sets synthetic profile state directly.
The intended POSIX hosts must run their own CI checks. An unload or bypass of
this tool route is outside the protected boundary.
