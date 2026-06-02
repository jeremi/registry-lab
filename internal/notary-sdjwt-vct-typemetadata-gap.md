# Issue brief: Notary should serve SD-JWT VC Type Metadata at the `vct` URL

Page type: issue / change brief
Product: Registry Notary (registry-notary)
Audience: registry-notary maintainers
Found: 2026-06-01, against the hosted lab (`citizen-notary.lab.registrystack.org`)
while testing OID4VCI issuance into a real walt.id holder wallet.

## Summary

The citizen Notary advertises an HTTPS `vct`
(`https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1`)
but serves no document there. A real wallet (walt.id, web wallet / wallet-api
`0.20.2`) mandatorily dereferences the `vct` as SD-JWT VC **Type Metadata**
during credential-offer setup and aborts the entire flow when it is not a `200`.
The offer never reaches the authorization step. To interoperate with strict
wallets, the Notary should serve a public SD-JWT VC Type Metadata document at the
`vct` URL.

Status: implemented in the sibling `registry-notary` source checkout after this
issue was written. The historical evidence below describes the hosted behavior
at discovery time. The hosted lab still needs rollout to an image containing the
source change before the live URL changes from auth failure to public Type
Metadata.

## Symptom (in the wallet)

Pasting the Notary's offer URI into the walt web wallet:

```
openid-credential-offer://?credential_offer_uri=https%3A%2F%2Fcitizen-notary.lab.registrystack.org%2Foid4vci%2Fcredential-offer
```

aborts in the wallet frontend before any redirect to eSignet:

```
GET /wallet-api/wallet/{id}/exchange/resolveVctUrl?vct=https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1
  -> 400
Error: VCT URL returns error: 400   (thrown in offer `setup`)
```

## Root cause

1. The issuer metadata declares a URL-shaped `vct`:

   ```
   GET https://citizen-notary.lab.registrystack.org/.well-known/openid-credential-issuer
   .credential_configurations_supported.person_is_alive_sd_jwt.vct
     = "https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1"
   ```

2. At discovery time, the Notary had **no route** for that path. Full route table
   (`crates/registry-notary-server/src/api.rs`, `pub fn router()`, ~L65-95):
   `/healthz`, `/ready`, `/admin/v1/reload`, `/openapi.json`,
   `/.well-known/evidence-service`, `/.well-known/evidence/jwks.json`,
   `/.well-known/openid-credential-issuer`, `/oid4vci/credential-offer`,
   `/oid4vci/nonce`, `/oid4vci/credential`, `/v1/claims[...]`, `/v1/formats`,
   `/v1/evaluations[...]`, `/v1/credentials[...]`, `/admin/v1/credentials/...`.
   There is nothing under `/credentials/...`.

3. In the code the `vct` is only an **opaque match key**, never a served
   document. It is compared, not dereferenced (`api.rs` ~L2126-2137:
   `if configuration.vct != vct { ... }`), and the operator docs call it
   "credential profile verifiable credential type URI"
   (`docs/sd-jwt-vc-conformance-profile.md`).

4. Because the global auth layer (composed in
   `crates/registry-notary-server/src/standalone.rs`) wraps the whole router,
   the unrouted path returned `401 auth.missing_credential` rather than `404`.
   The wallet's `resolveVctUrl` proxy surfaced that upstream non-200 as its own
   `400`.

Live evidence (probing the wallet's resolver directly against the running
wallet, `GET /wallet-api/wallet/{id}/exchange/resolveVctUrl?vct=...`):

| `vct` value | walt response |
|---|---|
| `https://citizen-notary…/credentials/citizen-civil-status/v1` | `400 : VCT URL returns error: 401 Unauthorized` |
| `urn:registrystack:credentials:citizen-civil-status:v1` | `400 : invalid URI scheme urn` |
| `citizen-civil-status` (bare string) | `400 : Unknown error` |

So changing the `vct` to a non-resolvable identifier does **not** help: walt
rejects non-`http(s)` `vct` outright, and there is no wallet-side toggle to make
resolution non-fatal (it is hard-wired in the demo-wallet frontend).

## Interop note (who is "wrong")

Per draft-ietf-oauth-sd-jwt-vc, dereferencing `vct` Type Metadata is a **MAY**
for consumers, and a `vct` need not be resolvable. walt is stricter than the
spec: it both requires `http(s)` and treats a non-200 as fatal. That is
arguably a walt limitation, but: (a) we do not control walt, and (b) serving
Type Metadata is the spec-aligned, durable fix that benefits any wallet and adds
real value (display strings, claim metadata, schema). Recommend the Notary serve
it rather than work around walt.

## Proposed change

Add a **public** Type Metadata endpoint, one per configured OID4VCI credential
configuration, served at the configured `vct` path, returning SD-JWT VC Type
Metadata JSON.

- **Route**: serve `GET` requests whose path equals the path component of a
  configured `vct` (for the lab config that is
  `/credentials/citizen-civil-status/v1`). Use either exact configured route
  registration or a wildcard handler such as `GET /credentials/{*path}` that
  reconstructs the absolute URL from the request scheme/host/path, finds the
  credential configuration whose `vct` exactly matches that URL, and returns
  its Type Metadata; 404 if none. Do **not** use a fixed
  `/credentials/{type}/{version}` shape because existing configs include nested
  paths such as `/credentials/dhis2/health-status/v1` and
  `/credentials/nagdi/climate-smart-input-voucher/v1`. Register in `api.rs`
  `router()` alongside the other public routes.
- **Auth**: must be reachable **unauthenticated**, the same way
  `/.well-known/openid-credential-issuer` and `/oid4vci/credential-offer` are.
  Add the `/credentials/` metadata surface to the public-path exemption in the
  auth middleware composed in `standalone.rs` (the same exemption those two
  already use).
- **CORS**: include the `/credentials/` metadata surface in the self-attestation
  wallet CORS path allow-list so browser-based wallets can dereference Type
  Metadata from allowed wallet origins.
- **Body**: source fields from the existing `Oid4vciCredentialConfigurationConfig`
  (already consumed by `oid4vci_configuration_metadata`, `api.rs` ~L2080:
  `scope`, `display_name`, `vct`, `cryptographic_binding_methods_supported`).
  `Oid4vciCredentialConfigurationConfig` has a single `claim_id`, not
  `allowed_claims`; use that `claim_id` for the OID4VCI credential
  configuration's claim metadata. If a future configuration can issue multiple
  claims, derive the list from that explicit configuration surface rather than
  from the credential profile's broader allow-list. Example document for
  `person_is_alive_sd_jwt`:

  ```json
  {
    "vct": "https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1",
    "name": "Person is alive",
    "description": "Civil-status attestation that the subject is alive.",
    "display": [
      { "locale": "en-US", "name": "Person is alive" }
    ],
    "claims": [
      {
        "path": ["person-is-alive"],
        "display": [{ "locale": "en-US", "label": "Person is alive" }],
        "sd": "always"
      }
    ]
  }
  ```

  `Content-Type: application/json`. Claim `path` entries should mirror the
  credential's actual SD-JWT claim names; for the current OID4VCI config shape,
  map from `claim_id`. Use `sd: "always"` for current Notary-issued claim
  disclosures because evaluated claim results are always emitted as
  selectively disclosable disclosures.

- **Optional, spec-nice-to-have**: add `"<vct>#integrity"` (an SRI hash of the
  Type Metadata document) next to `vct` in the issuer metadata so wallets can
  verify integrity. Not required by walt; can be a follow-up.

## Files to touch (registry-notary)

- `crates/registry-notary-server/src/api.rs`: new route in `router()` + handler.
- `crates/registry-notary-server/src/standalone.rs`: add the new path to the
  unauthenticated/public exemption list and wallet CORS path allow-list.
- `crates/registry-notary-server/tests/standalone_http.rs`: focused HTTP tests
  for public Type Metadata behavior.
- `crates/registry-notary-server/src/openapi.rs`, `docs/oid4vci-wallet-interop.md`,
  and `docs/sd-jwt-vc-conformance-profile.md`: document the public Type
  Metadata surface and response shape.
- Reuse `Oid4vciCredentialConfigurationConfig` (no config schema change needed;
  the `vct`, `display_name`, `scope`, and `claim_id` fields already exist).

## Acceptance test

```sh
VCT=https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1
curl -fsS "$VCT" | jq .vct            # 200, unauthenticated, vct echoes the URL
```

Focused server tests should cover:

- `GET /credentials/citizen-civil-status/v1` returns `200` without auth when it
  matches a configured `vct`.
- nested configured paths such as `/credentials/dhis2/health-status/v1` can be
  resolved, so the implementation is not limited to two path segments.
- an unknown `/credentials/...` path returns `404` without requiring auth.
- when `oid4vci.enabled = false`, the Type Metadata route returns `404`.
- browser wallet CORS headers are applied for allowed wallet origins.

Then in the walt wallet, the same offer URI must proceed **past** `setup`
(no `VCT URL returns error`) to the offer's grant step. (The next blocker after
this is the grant/authentication: walt is a public wallet and cannot complete the
`authorization_code` flow against eSignet, so the issuance path needs the
authenticated pre-authorized-code change; see
`internal/notary-preauthorized-code-issuance.md`.)

## Blast radius

The same gap applies to any Notary profile advertising a URL-shaped `vct`. The
hosted `opencrvs-dci-notary.yaml` and `dhis2-health-notary.yaml` configs also
set `vct`; if those are ever issued into a strict wallet they will hit the same
wall. Use exact configured path registration or a wildcard `/credentials/{*path}`
handler so nested credential type paths are covered.

## Definition of done

This work is done only when all of the following are true:

- `GET` without authentication to every `oid4vci.credential_configurations.*.vct`
  URL under the Notary issuer host, including issuer path prefixes such as
  `/notary/credentials/...`, returns `200`, `Content-Type: application/json`,
  and a JSON object whose `vct` exactly equals the requested absolute URL. For
  path-prefixed issuers, the reverse proxy must strip the issuer prefix before
  forwarding to Notary while preserving external scheme and host headers.
- The Type Metadata body includes `name`, `display[0].locale`,
  `display[0].name`, and one `claims` entry for the OID4VCI configuration's
  `claim_id`, with `path` equal to `[claim_id]`, `display[0].locale`,
  `display[0].label`, and `sd` equal to `"always"`.
- Unknown `/credentials/...` paths return `404` without requiring auth, and
  `oid4vci.enabled = false` makes the Type Metadata surface return `404`.
- Browser requests from configured self-attestation wallet origins to matching
  `/credentials/...` Type Metadata paths return `access-control-allow-origin`
  equal to the request `Origin`; preflights for allowed methods return `204` and
  include `access-control-allow-origin` and `access-control-allow-methods`.
- Existing authenticated Notary routes keep their current auth behavior:
  unauthenticated requests to credential issuance and admin routes such as
  `POST /v1/credentials` and `/admin/...` still return an auth failure (`401`
  or `403`), while the existing public credential-status URL behavior is
  unchanged.
- OpenAPI and operator/wallet docs describe the new public Type Metadata route,
  response shape, auth behavior, disabled behavior, and nested path support.
- Focused tests pass for successful metadata, nested metadata path, unknown
  metadata path, disabled OID4VCI metadata path, public auth exemption, CORS,
  and no regression to credential/status auth behavior.
- Repository verification passes with `cargo fmt --check`, focused
  `registry-notary-server` HTTP tests for the Type Metadata and CORS cases, and
  `cargo test -p registry-notary-server --features registry-notary-cel`.
- Hosted lab verification passes with:

  ```sh
  VCT=https://citizen-notary.lab.registrystack.org/credentials/citizen-civil-status/v1
  curl -fsSI "$VCT" | grep -i '^content-type: application/json'
  curl -fsS "$VCT" | jq -e '.vct == env.VCT and .claims[0].path == ["person-is-alive"] and .claims[0].sd == "always"'
  ```

- walt.id web wallet / wallet-api `0.20.2` resolves the same offer URI past VCT
  setup (no `VCT URL returns error`) to the offer's grant step. If the next
  failure is the grant/authentication blocker (walt cannot complete
  `authorization_code` against eSignet; see
  `internal/notary-preauthorized-code-issuance.md`), that failure is recorded
  separately and does not mask Type Metadata success.

## Implementation plan

- [ ] **Wave 1: contract and routing core**
  - Worker A: implement Type Metadata builder and route lookup in `api.rs`,
    using exact configured `vct` matching and nested path support.
  - Worker B: draft focused `standalone_http` tests against the agreed contract,
    including success, nested path, unknown path, and disabled OID4VCI cases.
  - Definition of done: tests fail before the route exists, then pass with the
    route; response status, content type, `vct`, `claim_id` path, and `sd` are
    asserted exactly.
  - Review checkpoint: review route matching, URL reconstruction, metadata JSON,
    and tests before touching auth/CORS/docs.

- [ ] **Wave 2: public access and browser behavior**
  - Worker A: add `/credentials/` Type Metadata paths to the unauthenticated auth
    exemption without widening `/v1/credentials`.
  - Worker B: add wallet CORS coverage for matching `/credentials/...` paths.
  - Worker C: add regression tests proving protected credential/status/admin
    routes still require auth.
  - Definition of done: unauthenticated metadata requests pass; wallet-origin
    CORS tests assert the response headers above; protected route regression
    tests return `401` or `403`.
  - Review checkpoint: review public path predicates and CORS predicates for
    over-broad matches before updating documentation.

- [ ] **Wave 3: docs, OpenAPI, and local verification**
  - Worker A: update OpenAPI with the public Type Metadata path and schemas.
  - Worker B: update wallet interop and SD-JWT VC conformance docs.
  - Worker C: run `cargo fmt --check`, focused HTTP tests for the Type Metadata
    and CORS cases, and
    `cargo test -p registry-notary-server --features registry-notary-cel`.
  - Definition of done: docs and OpenAPI match tested behavior exactly; all
    listed local commands pass or a concrete blocker is recorded.
  - Review checkpoint: final code review checks docs against tests and confirms
    no acceptance item above remains partial.

- [ ] **Wave 4: lab rollout and wallet validation**
  - Worker A: update the lab Notary source pin/image only after Notary changes
    are committed in its source repository.
  - Worker B: run hosted curl checks for the citizen VCT URL and any configured
    hosted OpenCRVS/DHIS2 VCT URLs.
  - Worker C: run the walt wallet offer flow and capture the first post-VCT
    result.
  - Definition of done: hosted curl checks pass exactly, walt proceeds past VCT
    setup, and any remaining eSignet issue is documented as a separate blocker.
  - Review checkpoint: release review verifies source commit, lab pin/image,
    hosted evidence, and wallet evidence before marking the feature done.
