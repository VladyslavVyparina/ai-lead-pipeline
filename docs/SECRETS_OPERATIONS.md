# Secrets operations — Infisical

Last reviewed: 2026-07-25.

Infisical is the secret source of truth. The application does not call an
Infisical SDK: the Infisical CLI injects ordinary environment variables only
into the API, worker, test, or Docker Compose process at startup. This prevents
application code and containers from holding an Infisical management credential.

## One-time project setup

1. The repository's checked-in `.infisical.json` selects the personal EU
   project `ai-lead-pipeline-dev`. It contains project metadata only, never a
   secret or token.
2. Add team members to that dev project only. Do not grant them access to the
   personal production project.
3. Each developer runs `infisical login --domain https://eu.infisical.com` once.
   They can then run `npm run dev`; no `infisical init` is required.
4. Add secrets in each environment. Use separate R2 buckets/credentials and
   separate OpenRouter keys/caps for dev, staging and prod.

For the exact developer onboarding steps, use
[Developer quick start](DEVELOPER_QUICKSTART.md).

## Required dev secrets

```dotenv
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<scoped-development-key>
OPENROUTER_MODEL=qwen/qwen3-32b
PER_LEAD_TOKEN_BUDGET=0.25
ARTIFACT_STORAGE_BACKEND=r2
R2_ACCOUNT_ID=<dev-account-id>
R2_ACCESS_KEY_ID=<dev-access-key>
R2_SECRET_ACCESS_KEY=<dev-secret>
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET_PRIVATE=ai-lead-private-dev
ARTIFACT_RETENTION_DAYS=90
ADMIN_TOKEN=<development-only-token>
```

`GOOGLE_PLACES_API_KEY` is optional: CSV/manual import and website enrichment
work without it. Add it only when lawful official Places discovery is required.

## Run commands

```powershell
# Automatic: local configuration when LOCAL_ENV_OWNER_KEY exists; otherwise
# development secrets injected only into this process from Infisical.
npm run dev

# Force the respective source when debugging the startup path.
npm run dev:local
npm run dev:infisical

# Run tests with dev secrets (use a disposable test database)
npm run test:dev

# Production Docker Compose; secrets are injected into Compose interpolation
npm run deploy:prod
```

Do not run production with a developer login. Use a production machine identity
with the narrowest project/environment permission. For GitHub Actions, use OIDC
machine identity—not a long-lived `INFISICAL_TOKEN` in GitHub Secrets.

## Rotation and access rules

- Never put `.env`, `.env.dev`, API keys, database passwords or R2 secrets in Git.
- A developer gets a dedicated dev OpenRouter key with low cap; revoke it when
  access ends. The team does not share an owner/root key.
- The repository owner may use a Git-ignored `.env.local`, `.env`, or `.env.dev`
  with a non-empty `LOCAL_ENV_OWNER_KEY`. This only chooses the local startup
  route; it does not grant access and must not be shared with developers. This
  workstation uses the separate Git-ignored `.ai-lead-owner.local` marker with
  `LOCAL_ENV_FILE=.env.dev` to select its existing `.env.dev` without altering
  any secret values.
- Use separate dev and prod R2 buckets. Do not grant developers production R2
  object access merely to test screenshot/artifact storage.
- Rotate immediately if a credential reaches chat, terminal history, a ticket or
  Git history.
