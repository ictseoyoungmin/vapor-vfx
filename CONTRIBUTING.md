# Contributing

This repository is an experimental source and research project. Public contribution and redistribution terms are pending license/rights review. This document describes the technical workflow, not a license grant.

## Start a change

Read `docs/WORK_STATUS_KO.md` and `docs/ARCHITECTURE_KO.md`. Use a scoped branch. Do not change preset defaults or public data/ABI contracts implicitly. Keep product changes and independent Lab experiments distinct; the latter must not become a runtime fallback.

- Edit canonical presets in `effects/presets.json`, shaders in `shaders/`, C/C++ contracts in `include/`, and C# source in `bindings/dotnet/`. Use the existing generation/sync tools rather than manually editing distribution copies.
- Add regression tests or a representative experiment, and preserve the prior output for visual A/B when appropriate. State the implementation, scene, seed, optics and limitations.
- Run the relevant checks. `python tools/check_sdk.py --source-only --lab` covers source and research checks; actual runtime checks are separate. For website-only changes use `python -m unittest discover -s tests -p test_pages.py` and `python tools/build_pages.py --assets auto`.
- Update the current owner document and work status only as needed. Put historical changes in `CHANGELOG.md`, not a new version-specific architecture file. Generated local output, compiled binaries, caches and historical bundles must not be added to Git.

## Review checklist

1. Which source/API path changed? Does it preserve existing users' behavior?
2. Which tests were actually run, and which used doubles or independent implementations?
3. Does visual quality improve at a comparable camera, material, grid and time? Is performance measured on the named host?
4. Does the package still work without optional assets/history? Is any new public file necessary and cleared for redistribution?
5. If blocked, report the blocker and exact reproduction command; never substitute a reference render for a native result.

See [validation](docs/VALIDATION_KO.md) and [publishing](docs/PUBLISHING_KO.md) for acceptance and public hosting.
