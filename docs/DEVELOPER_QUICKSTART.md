# Developer quick start

Use this guide if you have been invited to the `ai-lead-pipeline-dev`
Infisical project. You need access to **dev only**. Never request, copy or
share the repository owner's local `.env` files or production secrets.

## First time (Windows)

1. Clone the repository and open PowerShell in its root.
2. Install Python 3.10+, Node.js LTS, and the Infisical CLI.
3. Sign in to the invited account:

   ```powershell
   infisical login --domain https://eu.infisical.com
   ```

4. Install dependencies and browser support:

   ```powershell
   py -3.10 -m pip install -r requirements.txt
   py -3.10 -m playwright install chromium
   npm install
   ```

5. Start the application:

   ```powershell
   npm run dev
   ```

6. Open <http://127.0.0.1:8000/ui>.

## Every day

```powershell
npm run dev
```

The command obtains development secrets from Infisical for that process only.
It will never write them into the repository.

## If it does not start

- **"not authenticated"**: run `infisical login --domain https://eu.infisical.com`.
- **403 / project does not belong to selected organization**: you are signed in
  with the wrong account, or have not accepted the dev-project invitation. Log
  out with `infisical logout`, sign in to the invited account, then retry.
- **Port 8000 is already in use**: stop the existing local API, then rerun.
- **Missing Python package**: rerun `py -3.10 -m pip install -r requirements.txt`.

## Useful commands

```powershell
npm run test:dev    # tests with dev secrets injected
npm run verify:ai   # bounded OpenRouter smoke check
py -3.10 -m pytest -q  # deterministic tests, no Infisical needed
```

Production is deployed by an owner-controlled machine identity, not a
developer login. See [Secrets operations](SECRETS_OPERATIONS.md) for access
rules and [Architecture](ARCHITECTURE.md) for the system design.
