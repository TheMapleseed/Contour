# Security findings (codebase scan)

Summary of likely security issues from Bandit, grep patterns, and manual review. Excludes vendored libs and most `misc/`; focuses on `thonny/`.

**Fixed (this pass):** misc_utils check_output(list), urlopen scheme restriction (https only), terminal.py quoting (cwd/cmd), os_mp_backend path passed as repr, common.py nosec + comment, cp_back exec nosec, editors chmod 0o750, object_inspector repr length limit. **Fetch stack:** HTTPS only. **Page renders:** HTTPS + HTTP/2+ only (httpx http2=True, http1=False); requires `[fetch-httpx]`; no script execution. **Scraping/search:** Raw text/bytes only, no DOM, no JS (curl/urllib); model safe over open network.

---

## High / medium severity

### 1. **eval() in message parsing** — `thonny/common.py:292`
- **Issue:** `parse_message()` uses `eval(payload, _SAFE_EVAL_GLOBALS, {})` on backend message payload.
- **Status:** Mitigated: globals are restricted (no `__builtins__`, only literals and safe types). Bandit still reports B307.
- **Risk:** If the protocol or globals are extended with user-controllable or unsafe names, this becomes code execution.
- **Action:** Do not add unsafe names to `_SAFE_EVAL_GLOBALS`. Consider migrating to a format that allows `ast.literal_eval` or a small parser.

### 2. **Paramiko exec_command (shell injection)** — `thonny/backend.py:681`
- **Issue:** B601 – `self._client.exec_command(cmd_line_str, ...)`. Command string is built from `cwd`, `env`, `cmd_items` via `shlex.quote()`.
- **Status:** Currently built from IDE-controlled values; all user-derived parts are quoted.
- **Risk:** If any unquoted or unsanitized input is ever added to `cmd_line_str`, this becomes remote command injection.
- **Action:** Keep strict use of `shlex.quote()` for all dynamic parts; avoid string formatting for command construction.

### 3. **subprocess with shell=True** — `thonny/terminal.py` (lines 39, 42, 79, 130, 203)
- **Issue:** B602 – Multiple `subprocess.Popen(..., shell=True)` with string commands. `cmd`, `cwd`, and (on Windows) `term_cmd` influence the string.
- **Risk:** `cwd` and `cmd` are user-influenced (e.g. project path, “Run in terminal”). Malicious path or command could lead to shell metacharacter injection.
- **Action:** Prefer list argv + no shell where possible (e.g. Windows `wt` path already does). For cases that require a shell, ensure all user-derived parts are quoted (e.g. `shlex.quote` / `list2cmdline`) and document that `cwd`/`cmd` must be treated as untrusted.

### 4. **execute_system_command with shell=True** — `thonny/common.py:658–666`
- **Issue:** When `cmd.cmd_line` starts with `"!"`, it is passed as a single string with `shell=True` to `subprocess.Popen`.
- **Risk:** Command comes from shell/UI (user types `!...`). By design the user can run arbitrary shell commands; in a shared or locked-down environment this is a privilege/audit concern.
- **Action:** Document as intentional “system shell” feature. If supporting restricted environments, consider a policy or flag to disable `!` commands.

### 5. **MicroPython os.system with path interpolation** — `thonny/plugins/micropython/os_mp_backend.py:27, 31`
- **Issue:** `_cmd_execute_system_command`: `__minny_helper.os.system(%r)` with `cmd_line` from frontend. `_cmd_get_fs_info`: `os.system("stat -f -c '...' {path}")` with `path=cmd.path` (string format).
- **Risk:** If `cmd.path` or `cmd_line` contain shell metacharacters, device-side command injection. `%r` in the first call quotes the string for Python, but the device then runs it in its shell.
- **Action:** Validate/sanitize `cmd.path` (e.g. no `;`, `|`, `$()`, backticks, newlines). Prefer passing path as a single argument to a fixed stat command if the device API allows.

### 6. **subprocess.check_output with string (implicit shell)** — `thonny/misc_utils.py:169`
- **Issue:** `subprocess.check_output("mount")` — single string invokes shell.
- **Risk:** Low (no user input), but deprecated and inconsistent with safe practice.
- **Action:** Use `subprocess.check_output(["mount"], text=False)` and decode as needed, or `capture_output=True` with list.

### 7. **urlopen / allowed schemes** — `thonny/misc_utils.py`
- **Issue:** B310 – `urlopen(req, ...)` without restricting schemes.
- **Status:** Restricted to **https only** via `_require_https(url)`. HTTP/2+ is preferred where the server supports it (stdlib uses TLS).

### 8. **exec() for user code** — `thonny/plugins/cpython_backend/cp_back.py:1283`
- **Issue:** B102 – `exec(statements, global_vars)` runs user editor/REPL code.
- **Status:** Intentional; runs in separate backend process.
- **Risk:** Only if unsanitized external input (e.g. from network or untrusted file) is passed in; currently statements come from editor/REPL.
- **Action:** Keep statements sourced only from the IDE; do not pass unsanitized external input into this path.

---

## Lower severity / hardening

### 9. **Chmod 0o755 / 0o750** — `thonny/editors.py:482`, `thonny/backend.py:765`
- **Issue:** B103 – Permissive file modes. `editors.py` uses `0o755` for saved shebang scripts; `backend.py` uses `0o750` for remote shebang scripts.
- **Risk:** World/group executable; in shared systems could allow execution by others.
- **Action:** Prefer `0o750` (or `0o700` for user-only) where acceptable; document if 0o755 is required for compatibility.

### 10. **Try/except/pass** — multiple files (e.g. `editor_helpers.py:98`, `cp_back.py:538, 608, 768`, `chat.py:591`, `tktextext.py:287, 725`)
- **Issue:** B110 – Bare `except: pass` can hide failures and security-relevant errors.
- **Risk:** Low per site; overall can complicate debugging and incident response.
- **Action:** Catch specific exceptions; log or re-raise where appropriate; avoid silent pass in security-sensitive paths.

### 11. **ast.literal_eval on backend repr** — `thonny/plugins/object_inspector.py:399, 403, 445`
- **Issue:** `object_info["repr"]` comes from the running program; passed to `ast.literal_eval`.
- **Risk:** No code execution (literal_eval is safe); theoretically DoS or confusing output if repr is crafted.
- **Action:** Optional: limit length or wrap in try/except with a safe fallback for malformed repr.

### 12. **Hardcoded password strings (false positives)** — various
- **Issue:** B105 on strings like `'password'`, `'def'`, `';base64,'` in variable names or non-secret context.
- **Action:** No change needed; optional Bandit exclude for test_id B105 where appropriate.

### 13. **subprocess / import** — multiple files
- **Issue:** B404 (subprocess import) and B603 (subprocess call) reported in many places. Most are list argv, no shell.
- **Action:** Keep using list form and no shell where possible; document any place that must use shell or user-controlled args.

### 14. **Starting process with partial path** — e.g. `thonny/terminal.py:37`, `thonny/misc_utils.py:169`
- **Issue:** B607 – Using `"wt"` or `"mount"` without full path can be influenced by PATH.
- **Risk:** Low in normal use; in a compromised or locked-down environment PATH could point to a malicious binary.
- **Action:** Optional: use `shutil.which()` and/or full path for sensitive invocations; document PATH assumptions.

---

## Summary table

| # | Location | Severity | Type |
|---|-----------|----------|------|
| 1 | common.py:292 | Medium | eval (mitigated) |
| 2 | backend.py:681 | Medium | Paramiko / shell |
| 3 | terminal.py (multiple) | High | subprocess shell=True |
| 4 | common.py:658–666 | Medium | user shell command |
| 5 | os_mp_backend.py:27,31 | Medium | device os.system / path |
| 6 | misc_utils.py:169 | Low | subprocess string |
| 7 | misc_utils.py:555,584,604 | Medium | urlopen schemes |
| 8 | cp_back.py:1283 | Low | exec (by design) |
| 9 | editors.py:482, backend.py:765 | Low | chmod |
| 10 | multiple | Low | try/except pass |
| 11 | object_inspector.py | Low | literal_eval repr |
| 12–14 | various | Low | B105/B404/B603/B607 |

Run: `uv run bandit -r thonny -c pyproject.toml`, `uv run pip-audit`, and `uv run sigstore --help` (sign/verify artifacts) for full automated results. **Sigstore** (dev): in dependency-groups dev for keyless signing and verification of artifacts; see SECURITY.md.

---

## Other security concerns (post-scan)

- **HTTPS bypass (fixed):** `llama_download.download_file` now calls `_require_https(url)`. `base_flashing_dialog._download_to_temp` now requires HTTPS for remote URLs (rejects http), and calls `_require_https(download_url)` before fetching.
- **Path traversal in temp write (fixed):** `base_flashing_dialog._download_to_temp` now uses `os.path.basename(target_filename)` and rejects empty or `..`-containing names so the write stays inside the temp dir.
- **Remaining from table:** Paramiko exec_command (keep shlex.quote); terminal.py shell=True (user-derived cmd/cwd—quoted where added); `!` system commands (by design); device-side os.system for `!` (user intent); try/except pass (low); partial PATH for binaries (low).
- **Secrets:** API keys/tokens use workbench `get_secret`/`set_secret` (e.g. GitHub Copilot, Pydantic AI); no hardcoded secrets in code.
- **IPC:** workbench IPC uses `ast.literal_eval` on data from the other process; risk only if the other process is untrusted (same-machine only).
