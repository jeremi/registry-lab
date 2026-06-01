# Hosted Registry Lab Coolify Runbook

Visibility: internal operations note, not public documentation.

## Orientation (start here)

Hosted instance of the Registry Lab decentralized-evidence demo, running on
Jeremi's Hetzner box under Coolify alongside PitGenius. The sections below are the
setup spec; this Orientation block and "Current Deployment State And Active
Workarounds" near the bottom capture the live coordinates and reality.

Server and control plane:

```text
Host        Hetzner, root@95.217.225.112  (shared with PitGenius prod — be careful)
Coolify     https://cool.pitgenius.com  (v4.1.1)
API         https://cool.pitgenius.com/api/v1  (Bearer token minted in Coolify UI;
            keep it out of the repo — pass it as Authorization: Bearer <token>)
Project     registry-lab  uuid n8z8jgy608jbs36zera18t7c  (env: production)
SSH         read-only diagnostics only (docker ps/logs/exec on registry-lab
            containers). Config and secret changes go through the Coolify API/UI,
            never by editing files on the host.
```

Coolify apps (verified 2026-06-01):

```text
registry-lab    klhnsuoye8lwuamp0bko387t  compose.coolify.yaml          running:healthy
hosted-esignet  cewwn93kknzsfzicen9nul6v  compose.esignet-hosted.yaml   running:healthy
hosted-walt     (not created yet)         compose.walt-hosted.yaml      NOT DEPLOYED
```

`hosted-walt` is specified in this runbook and `compose.walt-hosted.yaml` exists,
but as of 2026-06-01 there is no Coolify app for it and
`wallet.lab.registrystack.org` does not resolve.

Repo and branch:

```text
Repo    github.com/jeremi/registry-lab  (public; this dir is its own git repo)
Branch  coolify-deploy  ← Coolify deploys from here. It is main minus .gitmodules
        and the 6 private vendor/ gitlinks (the hosted compose uses pre-built
        images, so the submodules are not needed and would break Coolify's
        --recurse-submodules clone). Land hosted fixes on coolify-deploy.
```

Key files (paths relative to `apps/registry-lab/`):

```text
compose.coolify.yaml            relay/notary/zitadel/static-metadata stack.
                                NOT compose.yaml — that is local dev.
compose.esignet-hosted.yaml     eSignet + mock-identity stack.
compose.walt-hosted.yaml        walt.id holder wallet (not yet deployed).
config/coolify/{relay,notary,openfn}/   service configs actually mounted in the
                                hosted deploy. A config-loader init container
                                clones the repo into named volumes; Coolify does
                                NOT seed compose bind mounts from the repo.
scripts/generate-demo-secrets.py        generates the demo secret/token set → .env
scripts/validate-hosted-deploy.py       preflight validator (see `just hosted-validate*`)
justfile                        task entrypoints (generate, hosted-validate,
                                citizen-login, smoke-*, ...)
.env / .env.local / .env.hosted see "Secrets And Bearer Tokens" below
internal/coolify-hosted-lab-deployment-spec.md   fuller design spec (companion)
```

Trigger a deploy via API (force rebuild) and watch it:

```sh
TOK=<coolify-api-token>; APP=klhnsuoye8lwuamp0bko387t
DUUID=$(curl -s -H "Authorization: Bearer $TOK" \
  "https://cool.pitgenius.com/api/v1/deploy?uuid=$APP&force=true" \
  | jq -r '.deployments[0].deployment_uuid')
curl -s -H "Authorization: Bearer $TOK" \
  "https://cool.pitgenius.com/api/v1/deployments/$DUUID" | jq -r .status
```

## Secrets And Bearer Tokens

`scripts/generate-demo-secrets.py` (`just generate`) writes the full demo set to
`.env`. Tokens are RANDOM per run, so each generation is a distinct set. Every
relay/notary runs `auth.mode: api_key` and stores only a SHA-256 fingerprint
server-side (the `*_HASH` env vars in Coolify); the plaintext bearer a client
presents is the matching `*_RAW` / `*_TOKEN` / `*_BEARER`
(`Authorization: Bearer <token>`, or the `X-Api-Key` header).

Three env files, three jobs:

```text
.env          local docker-compose stack (compose.yaml). Volatile — regenerated
              by `just generate`. Gitignored. Never commit.
.env.local    real upstream creds (OpenCRVS Farajaland client id/secret, the
              curated OPENCRVS evidence token). chmod 600, gitignored, NOT touched
              by the generator.
.env.hosted   durable bearer tokens for the HOSTED lab. chmod 600, gitignored,
              NOT clobbered by `just generate`. Load this to call the deployed
              *.lab.registrystack.org endpoints.
```

Call the deployed lab:

```sh
set -a; source .env.hosted; set +a
curl -H "Authorization: Bearer $CIVIL_METADATA_CLIENT_RAW" \
  https://civil-relay.lab.registrystack.org/metadata/policies
```

Inbound auth per service:

```text
civil / social / health relays   role tokens: metadata_client, evidence_source,
                                  evidence_only, row_reader, [aggregate_reader],
                                  shared_* (present the *_RAW)
dhis2-health-notary               DHIS2_EVIDENCE_CLIENT_TOKEN / _BEARER
opencrvs-dci-notary               OPENCRVS_EVIDENCE_CLIENT_TOKEN
citizen-civil-notary              OIDC (no static bearer)
```

Server-side, Coolify holds only the `*_HASH` values plus the two outbound raws the
services themselves need: `CIVIL_EVIDENCE_SOURCE_RAW` (citizen-notary → civil relay
source) and `OPENFN_SIDECAR_TOKEN_RAW` (dhis2-notary → openfn sidecar). Each
Coolify env key has a production copy (`is_preview: false`, used by the live deploy)
and an empty preview copy. To rotate the demo tokens: regenerate, PATCH the
`*_HASH` values (plus those two raws) into the `registry-lab` app production env,
then redeploy:

```sh
# per key, upserts by (key, is_preview); 201 on success, no duplicate created
curl -s -X PATCH -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  https://cool.pitgenius.com/api/v1/applications/$APP/envs \
  -d '{"key":"CIVIL_EVIDENCE_SOURCE_HASH","value":"sha256:...","is_preview":false}'
```

The exhaustive var lists are in "Required Registry Lab Secrets" below; they are
exactly what `generate-demo-secrets.py` emits (relay/notary hashes) plus the real
upstream creds from `.env.local`.

## Applications

Create three Coolify Docker Compose applications in the `registry-lab` project:

```text
Registry Lab       compose.coolify.yaml
Hosted eSignet     compose.esignet-hosted.yaml
Hosted walt        compose.walt-hosted.yaml
```

Do not use the local `compose.yaml` or `compose.esignet-live.yaml` for hosted
Coolify apps.

`Hosted walt` is a self-hosted walt.id holder wallet so the citizen Notary can
issue credentials into a real third-party wallet. It deploys only the holder
side (wallet-api + web wallet), fronted by a trimmed walt Caddy that serves the
web wallet and proxies `/wallet-api/*` to the backend on the same origin. The
issuer-api / verifier-api / portal are intentionally omitted because the
Registry Notary is the issuer.

## Domains

Assign domains in the Coolify UI, not through host ports:

```text
citizen-civil-notary              citizen-notary.lab.registrystack.org
civil-registry-relay              civil-relay.lab.registrystack.org
social-protection-registry-relay  social-relay.lab.registrystack.org
health-registry-relay             health-relay.lab.registrystack.org
static-metadata-publisher         metadata.lab.registrystack.org
zitadel                           zitadel.lab.registrystack.org
dhis2-health-notary               dhis2-notary.lab.registrystack.org
opencrvs-dci-notary               opencrvs-notary.lab.registrystack.org
esignet                           esignet.lab.registrystack.org
esignet-ui                        esignet-ui.lab.registrystack.org
caddy (Hosted walt)               wallet.lab.registrystack.org
```

The `Hosted walt` app exposes a single domain on its `caddy` service
(container port 7101). The wallet-api is reachable publicly at
`wallet.lab.registrystack.org/wallet-api/*` through that same Caddy; do not
assign it a separate domain.

Cloudflare DNS is already set up with `lab.registrystack.org` and
`*.lab.registrystack.org` in DNS-only mode. Before first certificate issuance,
confirm there is no effective `AAAA` record unless the host is reachable over
IPv6, and that any CAA policy permits Let's Encrypt.

## Required Registry Lab Secrets

Set these in the Registry Lab Coolify app before deploy:

```text
REGISTRY_LAB_POSTGRES_PASSWORD
ZITADEL_MASTERKEY
REGISTRY_NOTARY_AUDIT_HASH_SECRET
REGISTRY_NOTARY_ISSUER_JWK
CIVIL_EVIDENCE_SOURCE_RAW
OPENFN_SIDECAR_TOKEN_HASH
OPENFN_SIDECAR_TOKEN_RAW
OPENFN_DHIS2_HOST_URL
OPENFN_DHIS2_USERNAME
OPENFN_DHIS2_PASSWORD
DHIS2_EVIDENCE_CLIENT_TOKEN_HASH
DHIS2_EVIDENCE_CLIENT_BEARER_HASH
OPENCRVS_EVIDENCE_CLIENT_TOKEN_HASH
OPENCRVS_DCI_BASE_URL
OPENCRVS_DCI_CLIENT_ID
OPENCRVS_DCI_CLIENT_SECRET
OPENCRVS_DCI_SHA_SECRET
```

Set relay token hashes required by the mounted relay configs:

```text
REGISTRY_RELAY_AUDIT_HASH_SECRET
CIVIL_METADATA_CLIENT_HASH
CIVIL_EVIDENCE_SOURCE_HASH
CIVIL_EVIDENCE_ONLY_HASH
CIVIL_ROW_READER_HASH
SHARED_CIVIL_EVIDENCE_SOURCE_HASH
SOCIAL_METADATA_CLIENT_HASH
SOCIAL_EVIDENCE_SOURCE_HASH
SOCIAL_EVIDENCE_ONLY_HASH
SOCIAL_ROW_READER_HASH
SOCIAL_AGGREGATE_READER_HASH
SHARED_SOCIAL_EVIDENCE_SOURCE_HASH
HEALTH_METADATA_CLIENT_HASH
HEALTH_EVIDENCE_SOURCE_HASH
HEALTH_EVIDENCE_ONLY_HASH
HEALTH_ROW_READER_HASH
SHARED_HEALTH_EVIDENCE_SOURCE_HASH
```

Set image references explicitly in Coolify:

```text
REGISTRY_RELAY_IMAGE
REGISTRY_NOTARY_IMAGE
REGISTRY_NOTARY_OPENFN_SIDECAR_IMAGE
```

The preferred source for these values is product-owned images published by the
corresponding product repositories:

```text
REGISTRY_RELAY_IMAGE=<product-owned-registry-relay-image>
REGISTRY_NOTARY_IMAGE=<product-owned-registry-notary-image-with-registry-notary-cel>
REGISTRY_NOTARY_OPENFN_SIDECAR_IMAGE=<product-owned-openfn-sidecar-image>
```

Pin by digest when available:

```text
REGISTRY_RELAY_IMAGE=<product-owned-registry-relay-image>@sha256:...
REGISTRY_NOTARY_IMAGE=<product-owned-registry-notary-cel-image>@sha256:...
REGISTRY_NOTARY_OPENFN_SIDECAR_IMAGE=<product-owned-openfn-sidecar-image>@sha256:...
```

If product images are not published yet and Coolify is used to build locally,
use lab-local image tags such as `registry-relay:hosted`,
`registry-notary:hosted`, and `registry-notary-openfn-sidecar:hosted`. Do not
publish lab-built wrapper images under the canonical product image names. While
using those local tags, treat digest rollback as not yet satisfied and record
the selected Git revisions instead. The notary image used by the lab must be
built with `REGISTRY_NOTARY_FEATURES=registry-notary-cel`; the product workflow
publishes this as the `main-cel` / `sha-<commit>-cel` tag family before digest
pinning.

## Required eSignet Secrets

Set these in the hosted eSignet Coolify app before deploy:

```text
REGISTRY_LAB_ESIGNET_POSTGRES_PASSWORD
REGISTRY_LAB_ESIGNET_CLIENT_REDIRECT_URIS_JSON
```

`REGISTRY_LAB_ESIGNET_CLIENT_REDIRECT_URIS_JSON` must be a non-empty JSON array
of public HTTPS redirect URIs. The default hosted fallback is:

```json
["https://esignet-ui.lab.registrystack.org/callback"]
```

To let the walt wallet complete the OID4VCI authorization-code flow, add walt's
callback URI to this array (see the walt integration section below) and redeploy
the eSignet app so `esignet-seed` rewrites the seeded client's redirect URIs.

## Required walt Secrets

Set these in the Hosted walt Coolify app before deploy:

```text
WALT_DB_PASSWORD
WALT_AUTH_ENCRYPTION_KEY
WALT_AUTH_SIGN_KEY
WALT_AUTH_TOKEN_KEY
```

`WALT_AUTH_*` sign/encrypt the wallet's own login sessions. walt ships
hard-coded sample values for these in its public repo, so they are sourced from
the environment instead and fail the wallet-api startup if unset (no silent
fallback to a public key). Generate fresh values:

```sh
# 16-char (128-bit) keys
WALT_AUTH_ENCRYPTION_KEY="$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 16)"
WALT_AUTH_SIGN_KEY="$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 16)"
# >=32-char (256-bit) HS256 token key
WALT_AUTH_TOKEN_KEY="$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 48)"
WALT_DB_PASSWORD="$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 32)"
```

Optional overrides (defaults shown): `WALT_DB_NAME=waltid`,
`WALT_DB_USERNAME=waltid`, `WALT_IMAGE_TAG=0.20.2`,
`WALT_IMAGE_PREFIX=docker.io/`. Pin `WALT_IMAGE_TAG` to a digest when promoting
beyond the first deploy.

## Persistent Volumes

Registry Lab (actual names from `compose.coolify.yaml`):

```text
pgdata                              postgres (notary replay + zitadel; relays are file-backed)
redis-data
zitadel-seed
civil-registry-cache
social-protection-registry-cache
health-registry-cache
static-content                      static-metadata publisher output
cfg-relay / cfg-notary / cfg-data / cfg-pginit /
  cfg-openfn-tmpl / cfg-openfn-jobs / cfg-static-scripts
                                    config-loader-populated (the mounted configs)
```

Hosted eSignet (actual names from `compose.esignet-hosted.yaml`):

```text
esignet-pgdata-v3                   ┐ coupled set — see Current Deployment State:
mock-keystore                       │ reset all three together or you get
esignet-keystore                    ┘ KER-KMA-004 "No such alias" crash loops
esignet-redis-data
esignet-seed-data
es-pginit / es-uiconf / es-seed     config-loader-populated
```

Never mount eSignet seed output under repository `./output` in hosted mode.

Hosted walt:

```text
cfg-walt
cfg-walt-caddy
walt-pgdata
walt-data
```

`cfg-walt` / `cfg-walt-caddy` are populated by the config-loader from
`config/walt/` on each deploy. `walt-pgdata` holds the wallet database and
`walt-data` holds wallet-api runtime state (created keys/DIDs live in the DB).

## CI And Deploy

Configure this GitHub repository secret:

```text
COOLIFY_DEPLOY_WEBHOOK_URL
```

The `hosted-lab` workflow validates both compose files and the mounted hosted
configs. On `main`, after validation passes, it calls the Coolify deploy webhook
exactly once.

Local preflight:

```sh
just hosted-validate
just hosted-validate-test
```

Strict preflight from an environment that has the Coolify secret values:

```sh
just hosted-validate-strict
```

## walt Holder Wallet Integration

Standing up the `Hosted walt` app makes the wallet reachable; wiring it to the
citizen Notary so a credential can actually be issued takes a few more steps.

### Already wired in `config/walt/`

- New wallet accounts create an **Ed25519 `did:jwk`** key, matching the citizen
  Notary's `proof_signing_alg_values_supported: [EdDSA]` and
  `cryptographic_binding_methods_supported: [did:jwk]`.
- `did:web` resolution uses **HTTPS**, so the wallet can resolve the Notary's
  `did:web:citizen-notary.lab.registrystack.org` issuer DID to verify the VC.

### Deploy

1. Create the `Hosted walt` Coolify app (Docker Compose, `compose.walt-hosted.yaml`),
   on branch `coolify-deploy`, in the `registry-lab` project. Driven via the
   Coolify REST API the same way as the other two apps (mint a fresh API token;
   the previous one is not persisted).
2. Assign the `caddy` service the domain `wallet.lab.registrystack.org`
   (container port 7101). The `*.lab.registrystack.org` wildcard already resolves
   to the host, so no DNS change is needed.
3. Set the four `WALT_*` secrets (above) and deploy.
4. Verify the wallet loads at `https://wallet.lab.registrystack.org`, register an
   account, and confirm the generated DID is `did:jwk` over an Ed25519 key
   (`GET /wallet-api/wallet/{id}/dids` shows `did:jwk:...`).

### eSignet client + redirect wiring (authorization-code flow)

The citizen Notary's offer uses `grant_type=authorization_code` with eSignet
(`https://esignet.lab.registrystack.org/v1/esignet`) as the authorization
server, PKCE `S256`. In that flow the **wallet is the OAuth client**: eSignet
must know walt's `client_id` and redirect back to walt's callback. The Notary in
turn only accepts tokens whose client/audience it trusts:

```text
config/coolify/notary/citizen-civil-notary.yaml
  auth.oidc.allowed_clients / audiences      -> registry-lab-live-client
  oid4vci.accepted_token_audiences           -> [<notary>, registry-lab-live-client]
  self_attestation.citizen_clients.*         -> registry-lab-live-client
```

Two strategies, decided by what `client_id` walt actually presents (capture it
from the first authorize request via browser devtools or eSignet logs):

- **Reuse `registry-lab-live-client`** (simplest, if walt lets you pin the
  OID4VCI client_id): add walt's redirect URI to
  `REGISTRY_LAB_ESIGNET_CLIENT_REDIRECT_URIS_JSON` on the eSignet app and
  redeploy it (`esignet-seed` rewrites the client). No Notary change.
- **Dedicated `walt-lab-client`**: register a new eSignet client with walt's
  redirect URI, and add `walt-lab-client` to every Notary allow-list above
  (`allowed_clients`, `audiences`, `accepted_token_audiences`,
  `citizen_clients.allowed_client_ids` / `allowed_audiences`). Cleaner
  separation; touches both the Notary config and the eSignet seed.

This is the one spot expected to need a round of iteration; the wallet-neutral
probe below isolates whether a failure is in the Notary path or the wallet path.

### Smoke

1. Confirm the Notary issuance path is green wallet-neutrally first:

   ```sh
   just citizen-oid4vci-login
   just citizen-oid4vci-code
   ```

2. Then drive the real wallet per `docs/wallet-interop-testing.md` (generate an
   `openid-credential-offer://` URI from the running citizen Notary and feed it
   to the walt web wallet / `useOfferRequest`). Record the result in the
   evidence checklist there.

## Current Deployment State And Active Workarounds

Verified 2026-06-01. Reflects what is actually running, which differs from the
spec above in a few places.

- **Deployed apps:** `registry-lab` and `hosted-esignet`, both `running:healthy`;
  all of their domains serve (relays/notaries 401 auth-gated, zitadel UI 200,
  esignet-ui 200). `hosted-walt` not deployed yet.
- **Images are lab-built, not product-owned.** A GitHub Actions workflow
  (`.github/workflows/build-images.yml`, job `build-hosted-images`) compiles the
  three images on amd64 and pushes to
  `ghcr.io/jeremi/registry-{relay,notary,notary-openfn-sidecar}` (public,
  digest-pinned in Coolify via `REGISTRY_*_IMAGE`). Relay built with
  `spdci-api-standards,standards-cel-mapping,ogcapi-edr`; notary with
  `registry-notary-cel`. GHCR push needs login with a PAT (`SUBMODULES_PAT`,
  scopes `repo`+`write:packages`+`read:packages`); the login fix lives on branch
  `ci-ghcr-pat`, not yet merged to `main`.
- **Notary healthcheck + OpenCRVS URL workarounds** are active because the
  vendored `registry-notary` (v0.3.0) is older than the configs assume. Fix path:
  bump `vendor/registry-notary` to the dev's image version, then revert both (see
  Runtime Pitfalls).
- **eSignet keystore ↔ DB coupling.** The MOSIP PKCS12 master keystore lives on
  named volumes `mock-keystore` + `esignet-keystore` (mounted at
  `/home/mosip/keystore` via `MOSIP_KERNEL_KEYMANAGER_HSM_CONFIG_PATH`), coupled
  with DB volume `esignet-pgdata-v3`. These three are a set: to reset eSignet, bump
  the DB suffix AND recreate both keystore volumes together, else `KER-KMA-004 No
  such alias` crash loops.
- **esignet-ui target port.** Its Coolify domain is set to
  `https://esignet-ui.lab.registrystack.org:3000` — the `:3000` is the target
  container port (nginx listens only on 3000; public stays 443). Without it
  Traefik routes to the lowest exposed port (80, dead) and 502s.
- **Identity flow verified** end-to-end via Playwright (authorize → eSignet login
  UIN `NID-1001` / OTP `111111` → consent → callback with a real auth code). The
  code→token→VC leg needs the seeded client private key and was not run.
- **Open follow-ups:** rotate the GHCR PAT and the OpenCRVS/DHIS2 creds (pasted
  plaintext); merge `ci-ghcr-pat` to `main`; bump `vendor/registry-notary` and
  revert the two workarounds; seed static-metadata content; `docker volume rm` the
  orphaned `esignet-pgdata` and `esignet-pgdata-v2` (superseded by `-v3`).

## Runtime Pitfalls

- The citizen notary `auth.oidc.issuer` must exactly match the hosted eSignet
  discovery document's `issuer`. Verify with:

  ```sh
  curl -fsS https://esignet.lab.registrystack.org/v1/esignet/oidc/.well-known/openid-configuration | jq -r .issuer
  ```

- The deployed `registry-notary` image must include the product-owned
  `registry-notary healthcheck` subcommand. The hosted compose intentionally
  uses that subcommand instead of `curl` so the distroless image can report
  health without a shell or package manager.
  - CURRENT REALITY: the deployed lab-built image (v0.3.0) has NO `healthcheck`
    subcommand, so the hosted compose temporarily uses `registry-notary --version`
    as the liveness probe. Revert once the notary image is bumped (see Current
    Deployment State).
- The OpenCRVS notary config uses product-owned `${OPENCRVS_DCI_BASE_URL:?...}`
  expansion inside `registry-notary`; do not add a shell entrypoint wrapper for
  that service.
  - CURRENT REALITY: the deployed binary does NOT expand `${...}` in its config,
    so `config/coolify/notary/opencrvs-dci-notary.yaml` hardcodes the Farajaland
    URLs and `OPENCRVS_DCI_BASE_URL` is vestigial. Revert once the notary image
    supports expansion.
- The hosted eSignet compose corrects the seeded client redirect URIs after the
  local seed script runs. Check `esignet-seed` logs first if hosted login fails.
- The validator proves hosted artifacts are deploy-safe, but it cannot inspect
  Coolify UI domain assignments or Cloudflare settings. Verify those separately
  before phone-wallet testing.
- The `Hosted walt` domain must point at the `caddy` service, not at `wallet-api`
  or `waltid-demo-wallet` directly. walt's web wallet calls its backend at a
  relative `/wallet-api` path on its own origin; only the Caddy ingress routes
  that path to `wallet-api:7001`. Pointing the domain elsewhere breaks API calls
  from the browser.
- `config/walt/auth.conf` reads `WALT_AUTH_*` from the environment with no
  fallback. If any is unset the wallet-api fails to start (by design). Check the
  wallet-api logs for a HOCON substitution error if it crash-loops on boot.
- walt publishes amd64 + arm64 images; the Hetzner host is amd64, so the pinned
  tag resolves correctly there. Do not assume the local Apple-Silicon pull
  matches what deploys.
