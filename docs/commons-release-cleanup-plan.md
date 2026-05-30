# Commons Release Cleanup Plan

Date: 2026-05-30

## Definition Of Done

This work is complete only when every criterion below is verified:

- `registry-platform` exposes tested named profiles or helpers for shared OIDC, audit, and OID4VCI security flows.
- `registry-relay` and `registry-notary` compile against the sibling Platform checkout without relying on dirty local source trees.
- `registry-relay` and `registry-notary` each provide a documented `scripts/check-platform-compat.sh` command.
- `registry-manifest` is documented as the contract and schema kernel and provides a documented contract-kernel check.
- `registry-lab` provides `just commons-check` and it runs Platform, Manifest, Relay, Notary, and selected Lab smoke checks from sibling source dirs by default.
- Focused tests prove strict OIDC `typ` handling, keyed audit-chain bootstrap from persisted tails, and OID4VCI nonce replay rejection.
- No Lab vendor pin or generated output is changed before source repo branches are committed and reviewed.
- Every changed repo has either a passing verification command or a recorded external-service blocker with the exact command and failure reason.

## Wave 1: Platform Profiles

Checklist:

- Add OIDC verifier profiles for Relay access tokens, Notary access tokens, and Notary federation request JWTs.
- Add audit profiles for production keyed chain hashing and explicit dev-only unkeyed mode.
- Add OID4VCI credential-endpoint policy and nonce-consume helper.
- Keep low-level structs available for advanced callers.
- Add focused Platform tests for each new helper surface.

Done when:

- `cargo test -p registry-platform-oidc token_verifier_profiles_set_safe_related_token_defaults --lib` passes.
- `cargo test -p registry-platform-oidc federation_request_profile_binds_single_audience_and_type --lib` passes.
- `cargo test -p registry-platform-audit audit_profile --lib` passes.
- `cargo test -p registry-platform-oid4vci credential_endpoint_policy_and_nonce_helper_consume_once --lib` passes.

Review checkpoint:

- Review API shape before consumer migration.
- Do not approve helpers that only rename raw config bags without removing app-side security decisions.

## Wave 2: Consumer Migration

Checklist:

- Migrate Relay standard OIDC and audit-chain wiring to Platform profiles.
- Migrate Notary OIDC, audit, and OID4VCI nonce wiring to Platform profiles.
- Add or preserve focused consumer tests for strict token `typ`, keyed audit-chain tail bootstrap, and nonce replay rejection.
- Keep unrelated route, demo, generated, or SDK rewrites out of this wave.

Done when:

- `REGISTRY_PLATFORM_SOURCE_DIR=../registry-platform registry-relay/scripts/check-platform-compat.sh` passes from the Lab sibling layout.
- `REGISTRY_PLATFORM_SOURCE_DIR=../registry-platform registry-notary/scripts/check-platform-compat.sh` passes from the Lab sibling layout.
- No compatibility script reports zero tests for a required focused test.

Review checkpoint:

- Review Relay and Notary diffs separately.
- Do not mark either app done until its repo-owned compatibility script passes.

## Wave 3: Manifest Kernel

Checklist:

- Document Manifest as the reusable contract and schema kernel.
- Add `registry-manifest/scripts/check-contract-kernel.sh`.
- Validate built-in profiles and publish any passed consumer manifests into `target/contract-kernel`.
- Document the command in the Manifest root and crate READMEs.

Done when:

- `scripts/check-contract-kernel.sh ../registry-lab/config/static-metadata/metadata.yaml ../registry-lab/config/relay/*.metadata.yaml` passes from `registry-manifest`.
- The command exits nonzero on invalid consumer manifests.

Review checkpoint:

- Review Manifest boundaries separately from Platform security boundaries.
- Do not add speculative abstractions without a real consumer check.

## Wave 4: Lab Gate

Checklist:

- Add `registry-lab/scripts/commons-check.sh`.
- Add `just commons-check`.
- Run sibling Platform tests, Manifest kernel check, Relay compatibility check, Notary compatibility check, `relay-zitadel`, and `notary-redis`.
- Use temporary output for checks that would otherwise write generated env files.

Done when:

- `just commons-check` starts from a clean Lab checkout and prints the repo and command being run.
- It does not edit vendor pins, generated metadata, demo output, or committed fixtures.
- It passes, or its only failures are documented external-service blockers from Lab smoke checks.

Review checkpoint:

- Review command output and environment assumptions.
- Do not approve if success depends on undocumented services, secrets, or generated local files.

## Wave 5: Final Release Review

Checklist:

- Run formatting and repo-owned compatibility commands in each changed repo.
- Run `just commons-check` from Lab.
- Self-review diffs for unrelated churn and dirty-worktree leakage.
- Update Lab vendor pins only after source repo changes are committed and reviewed.

Done when:

- Every verification command is recorded with pass/fail status.
- Remaining risks are concrete, file-referenced, and not required for this release.
- Source repos contain all product-code changes before Lab pins move.

Review checkpoint:

- Final review validates source repo commits, Lab command output, vendor pin policy, and remaining risks.

## Implementation Plan

- [ ] Wave 1 in parallel: OIDC, audit, and OID4VCI workers implement disjoint Platform helpers and tests. Definition of done is the four focused Platform test commands listed in Wave 1 passing.
- [ ] Wave 2 in parallel: Relay worker owns Relay migration and script, Notary worker owns Notary migration and script. Definition of done is both compatibility scripts passing and required focused tests running at least one test each.
- [ ] Wave 3 in parallel with Wave 2 review: Manifest worker owns docs and `check-contract-kernel.sh`. Definition of done is the Manifest kernel command passing against Lab consumer manifests.
- [ ] Wave 4 after Waves 2 and 3 review: Lab worker owns `commons-check`. Definition of done is `just commons-check` running all repo gates and Lab smokes without writing generated or vendor files.
- [ ] Wave 5: reviewer worker performs final diff review while the parent agent runs final verification. Definition of done is documented command output, no unrelated diff, and no feature marked complete without passing tests or a named external blocker.
