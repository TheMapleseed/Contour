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
- **Sigstore** (dev): `sigstore` is in the dev group for signing and verifying artifacts (keyless signing, verification against the Sigstore transparency log). Use `uv run sigstore verify-artifact <file> --certificate <cert> --signature <sig>` or see [sigstore-python](https://sigstore.github.io/sigstore-python/) for signing releases or verifying supplied materials.

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

Report vulnerabilities responsibly (e.g. via the project’s issue tracker or security contact).
