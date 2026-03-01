# Security and hardening (Contour / Thonny)

This document maps common Python hardening practices to Contour and what maintainers do (or should do).

## 1. Code-level hardening

- **Sanitize inputs:** External data (e.g. API responses, file contents opened in the IDE) is not blindly executed. User code execution is intentional and runs in an isolated backend process. Pydantic is used where applicable (e.g. Pydantic AI assistant).
- **Dangerous functions:**
  - `eval()` in `thonny/common.py` uses a restricted globals dict (no `__builtins__`, only literals and safe types) to parse messages from the **own backend subprocess**. Do not extend the allowed globals with user-controllable or unsafe names.
  - `exec()` in the CPython backend runs **user code** by design (IDE) in an isolated process; do not pass unsanitized external input.
  - `os.system()` is used only with fixed strings (e.g. terminal clear). Do not pass unsanitized user input.
- **SQL:** No direct SQL or user-driven SQL in the IDE; not applicable unless a plugin adds it (use parameterized queries / ORM then).
- **Errors:** Debug mode is off by default (`general.debug_mode`). When it is off, the workbench and shell show only short error messages to users; full tracebacks are logged to frontend.log and shown in the UI only when debug mode is on.

## 2. Dependencies and environment

- **Isolation:** Contour uses a virtual environment by default (`.venv`); system install is optional. Each project can have its own env.
- **Scanning:**
  - **Bandit** (dev): `uv run bandit -r thonny -c pyproject.toml` to find common issues. Excludes `thonny/vendored_libs` and tests.
  - **pip-audit** (dev): `uv run pip-audit` to check dependencies against known vulnerabilities. Run after dependency changes.
- **Pinning:** Dependencies are pinned in `uv.lock` (or equivalent lockfile). Use the lockfile for reproducible installs.
- **Sigstore** (dev): Think of Sigstore as a **digital notary** for your code. Instead of a physical stamp or a permanent secret key (which can be stolen), it uses your GitHub identity to prove that your specific GitHub Action produced the files. No long-lived keys; each asset gets a `.sig` and `.cert` next to it on the release. See "Release flow and Sigstore" below.

## 3. Data and secrets

- **No hardcoded secrets:** API keys (e.g. Pydantic AI, OpenAI, GitHub Copilot) are stored via the workbench secret API (`get_secret` / `set_secret`), not in source. Use environment variables or a secrets manager for CI/deployment.
- **Passwords:** Not stored in code; use the same secret API or system keyring where applicable.
- **Encryption:** For sensitive data at rest, use the `cryptography` library (e.g. Fernet). Not currently required for default IDE use.

## 4. Deployment hardening

- **Non-root:** Run the application under a dedicated, low-privilege user when deploying or when running in a shared environment.
- **HTTPS:** For any web or API access (e.g. AI backends), use TLS. The project uses `certifi` for TLS verification where applicable.
- **Resources:** For web-facing or network-exposed services, add rate limiting and request size limits. The IDE itself is typically local; plugins that open ports should consider this.

## Running security checks (developers)

With dev dependencies installed (e.g. `uv sync --group dev`):

```bash
uv run bandit -r thonny -c pyproject.toml
uv run pip-audit
uv run sigstore --help   # sign/verify artifacts
```

## Release flow and Sigstore (beta: 0.1.0)

**What are the assets?** For this Python project they are the same files you’d send to PyPI: the **wheel** (`.whl` — ready-to-install) and the **tarball** (`.tar.gz` — source). The release workflow builds these, uploads them to the GitHub release, then has Sigstore sign them.

**How the "notary" works:** (1) **Identity** — When the GitHub Action runs, it gets a temporary "ID badge" (OIDC token) from GitHub. (2) **Signing** — Sigstore checks that badge, confirms it’s this repo’s workflow, and creates a `.sig` and `.cert` for each file. (3) **Public record** — The event is recorded in Rekor (a public, append-only log). If someone swapped your code for a tampered version, the signature wouldn’t match and a user’s verify command would fail.

**What actually happens:**

1. **Publish the release** — On GitHub, create a release from a tag (e.g. `v0.1.0`) and click Publish (you don’t need to upload files manually).
2. **Build and sign** — [`.github/workflows/release-sign.yml`](.github/workflows/release-sign.yml) runs: builds `.whl` and `.tar.gz`, uploads them to the release, then runs the Sigstore action with `release-signing-artifacts: true` so every asset gets a `.sig` and `.cert` on the release page. The workflow uses `id-token: write` (the "ID badge") and `contents: write` (to attach the signatures).
3. **Verify (downloaders)** — Download the asset and its `.sig` and `.cert` from the release, then run the verify command below.

### Verifying release signatures (downloaders)

Release assets are signed with [Sigstore](https://sigstore.dev) (keyless). After downloading a release file and its `.sig` and `.cert` from the same GitHub release:

**Option A — sigstore (Python)**  
`pip install sigstore` (or `uv add sigstore`), then:

```bash
sigstore verify artifact path/to/contour-0.1.0.tar.gz \
  --certificate path/to/contour-0.1.0.tar.gz.cert \
  --signature path/to/contour-0.1.0.tar.gz.sig
```

Or with the project dev env: `uv run sigstore verify artifact <file> --certificate <file>.cert --signature <file>.sig`.

**Option B — Cosign**  
Install [cosign](https://docs.sigstore.dev/cosign/installation/), then:

```bash
cosign verify-blob <asset> \
  --signature <asset>.sig \
  --certificate <asset>.cert \
  --certificate-identity "https://github.com/TheMapleseed/Contour/.github/workflows/release-sign.yml@refs/tags/v0.1.0" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Use the tag that matches your download (e.g. `refs/tags/v0.1.0` for release v0.1.0).

The certificate is short-lived (Fulcio + GitHub OIDC); the signature is in Rekor. This confirms the artifact was produced by this repo’s release workflow.

Report vulnerabilities responsibly (e.g. via the project’s issue tracker or security contact).
