=======
Contour
=======

**Contour** is a Python IDE (based on Thonny) with AI chat (Pydantic AI, local GGUF models) and Marimo notebooks. This repo provides the **Contour** launcher and install script.

Requirements
------------
- **Python 3.14+** on your PATH as ``python3.14``
- Optional: **uv** (faster installs); otherwise ``pip`` is used

Build (developers)
------------------
From the repo root, run checks and formatting before committing:

.. code-block:: bash

   ./format-and-check.sh

Requires dev dependencies: ``uv sync --group dev`` (or ``pip install -e ".[dev]"``). To build a wheel (optional): ``uv build`` (output in ``dist/``).

Installation
------------
From the repo root (ensure ``install`` and ``Contour`` are executable: ``chmod +x install Contour``).

**Option A — venv (recommended)**

.. code-block:: bash

   ./install
   # Then open a new terminal or: source ~/.zshrc   (or source ~/.bashrc)
   Contour

**Option B — system Python 3.14**

.. code-block:: bash

   ./install --system
   Contour --system

  ``./install`` adds the repo to your PATH in ``~/.zshrc`` / ``~/.bashrc``. Use ``./install --force`` (or ``./install --force --system``) to reinstall or upgrade. If you run ``./Contour`` from the repo without ``./install`` first, Contour will create a venv and install on first run and add PATH for you.

**What gets installed:** Extras ``pydantic-ai``, ``llama-cpp``, ``marimo`` (and ``git`` when available) for AI chat, local GGUF models, and Marimo notebooks.

Runtime
-------
- **Default (venv):** ``Contour`` from anywhere, or ``./Contour`` from the repo — uses ``.venv`` in the repo.
- **System Python:** ``Contour --system`` or set ``CONTOUR_USE_SYSTEM=1`` — uses system Python 3.14. After a system install you can also run ``python3.14 -m thonny`` from anywhere.

Marimo
------
A **Marimo** tab appears in the left panel (next to Files). Use it to start `marimo <https://github.com/marimo-team/marimo>`_ (reactive Python notebook). Marimo is installed by default.

Scripts reference
-----------------
- **install** — install or upgrade (``./install``, ``./install --system``, ``./install --force``).
- **Contour** — run the IDE (see ``Contour`` in the repo root). Full **Contour** script:

.. code-block:: bash

   #!/usr/bin/env bash
   # Contour launcher: run Thonny from this repo. Requires Python 3.14+.
   # Default: use a venv in .venv (create and install on first run).
   # Option: CONTOUR_USE_SYSTEM=1 or ./Contour --system to use system Python instead.
   set -e
   DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   cd "$DIR"

   # Prefer --system flag, then CONTOUR_USE_SYSTEM env (1, true, yes)
   USE_SYSTEM=
   [[ "$1" == "--system" ]] && { USE_SYSTEM=1; shift; }
   if [[ -z "$USE_SYSTEM" && -n "$CONTOUR_USE_SYSTEM" ]]; then
     case "$CONTOUR_USE_SYSTEM" in 1|true|yes|TRUE|YES) USE_SYSTEM=1;; esac
   fi

   # Require Python 3.14 or newer
   if ! command -v python3.14 &>/dev/null; then
     echo "Contour requires Python 3.14 or newer. Install it and ensure python3.14 is on your PATH." >&2
     exit 1
   fi

   if [[ -n "$USE_SYSTEM" ]]; then
     # System mode: install into system Python 3.14, run with it (no venv)
     if ! python3.14 -c "import thonny" &>/dev/null; then
       echo "First-time setup: installing Contour into system Python (with AI and local model support)..." >&2
       if command -v uv &>/dev/null; then
         uv pip install --python python3.14 --system -e ".[pydantic-ai,llama-cpp,marimo]" -q
       else
         python3.14 -m pip install -e ".[pydantic-ai,llama-cpp,marimo]" -q
       fi
       echo "Installed." >&2
     fi
     if ! command -v Contour &>/dev/null; then
       CONTOUR_PATH_LINE="export PATH=\"$DIR:\$PATH\""
       for rc in ~/.zshrc ~/.bashrc; do
         if [[ -f "$rc" ]] && ! grep -Fq "$DIR" "$rc" 2>/dev/null; then
           echo "" >> "$rc"
           echo "# Contour launcher (added by Contour first run)" >> "$rc"
           echo "$CONTOUR_PATH_LINE" >> "$rc"
           echo "Added repo to PATH in $rc — open a new terminal or run: source $rc" >&2
         fi
       done
     fi
     exec python3.14 -m thonny "$@"
   fi

   # Venv mode (default): create .venv and install into it if not present
   VENV_PY="$DIR/.venv/bin/python"
   if [[ ! -x "$VENV_PY" ]]; then
     echo "First-time setup: creating venv and installing Contour (with AI and local model support)..." >&2
     if command -v uv &>/dev/null; then
       uv venv --python python3.14 "$DIR/.venv"
       uv pip install --python "$VENV_PY" -e ".[pydantic-ai,llama-cpp,marimo]" -q
     else
       python3.14 -m venv "$DIR/.venv"
       "$VENV_PY" -m pip install -e ".[pydantic-ai,llama-cpp,marimo]" -q
     fi
     echo "Installed. Run Contour again to start." >&2
   fi

   if ! command -v Contour &>/dev/null; then
     CONTOUR_PATH_LINE="export PATH=\"$DIR:\$PATH\""
     for rc in ~/.zshrc ~/.bashrc; do
       if [[ -f "$rc" ]] && ! grep -Fq "$DIR" "$rc" 2>/dev/null; then
         echo "" >> "$rc"
         echo "# Contour launcher (added by Contour first run)" >> "$rc"
         echo "$CONTOUR_PATH_LINE" >> "$rc"
         echo "Added repo to PATH in $rc — open a new terminal or run: source $rc" >&2
       fi
     done
   fi

   exec "$VENV_PY" -m thonny "$@"

**Full model-download script (``scripts/download_llama_model.py``)** — downloads a GGUF into the same models directory Contour uses on all OSes. Run from repo root, e.g. ``python3 scripts/download_llama_model.py --hf-repo TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF --hf-file tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf`` or ``--list`` to list existing models:

.. code-block:: python

   #!/usr/bin/env python3
   """
   Download a GGUF model into the same models directory Contour/Thonny uses on all OSes.

   This script only downloads the .gguf file. It does NOT need Metal, CUDA, or ROCm.
   To *run* the model with GPU, install llama-cpp-python for your OS/GPU (once per machine):

     macOS (Apple Silicon, Metal):
       CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --no-cache-dir

     Linux/Windows (Nvidia, CUDA 12.x):
       pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

     Linux/Windows (AMD, ROCm): build from source with -DGGML_HIPBLAS=on (see llama-cpp-python docs).

     CPU only (any OS):
       pip install llama-cpp-python

   Usage:
     python3 scripts/download_llama_model.py --url "https://example.com/model.Q4_K_M.gguf"
     python3 scripts/download_llama_model.py --hf-repo REPO --hf-file FILE.gguf
     python3 scripts/download_llama_model.py --list
   """

   from __future__ import annotations

   import argparse
   import os
   import sys
   import urllib.error
   import urllib.request


   def get_models_dir() -> str:
       """Return the same models directory used by Contour/Thonny on this OS."""
       base = os.environ.get("THONNY_USER_DIR", "").strip()
       if base:
           base = os.path.expanduser(base)
       elif sys.platform == "win32":
           base = os.path.join(
               os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming")),
               "Thonny",
           )
       elif sys.platform == "darwin":
           base = os.path.expanduser("~/Library/Thonny")
       else:
           base = os.path.join(
               os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
               "Thonny",
           )
       return os.path.join(base, "models")


   def download_file(url: str, dest_path: str, force: bool = False) -> bool:
       """Download url to dest_path. Return True if downloaded, False if skipped (exists and not force)."""
       if os.path.isfile(dest_path) and not force:
           print(f"Already exists (use --force to replace): {dest_path}")
           return False
       os.makedirs(os.path.dirname(dest_path), exist_ok=True)
       print(f"Downloading {url}")
       print(f"  -> {dest_path}")
       req = urllib.request.Request(url, headers={"User-Agent": "Contour-LLM-Download/1.0"})
       try:
           resp = urllib.request.urlopen(req)
       except urllib.error.URLError as e:
           if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
               print(
                   "SSL certificate verification failed. On macOS, run:\n"
                   "  /Applications/Python 3.x/Install Certificates.command\n"
                   "or ensure your system has valid CA certificates.",
                   file=sys.stderr,
               )
           raise
       with resp:
           total = resp.headers.get("Content-Length")
           total = int(total) if total else None
           size = 0
           chunk_size = 1024 * 1024  # 1 MiB
           with open(dest_path, "wb") as f:
               while True:
                   chunk = resp.read(chunk_size)
                   if not chunk:
                       break
                   f.write(chunk)
                   size += len(chunk)
                   if total and total > 0:
                       pct = min(100, 100 * size / total)
                       mb = size / (1024 * 1024)
                       total_mb = total / (1024 * 1024)
                       print(f"\r  {pct:.1f}% ({mb:.1f} / {total_mb:.1f} MiB)", end="", flush=True)
           if total:
               print()
       print("Done.")
       return True


   def hf_url(repo: str, filename: str, revision: str = "main") -> str:
       """Build Hugging Face direct download URL."""
       repo = repo.strip().strip("/")
       if "/" in repo:
           org, name = repo.split("/", 1)
       else:
           org, name = repo, repo
       return f"https://huggingface.co/{org}/{name}/resolve/{revision}/{filename}"


   def main() -> int:
       ap = argparse.ArgumentParser(
           description="Download a GGUF model into Contour/Thonny models directory (same on all OSes)."
       )
       ap.add_argument("--url", metavar="URL", help="Direct URL to a .gguf file")
       ap.add_argument("--hf-repo", metavar="REPO", help="Hugging Face repo (e.g. TheBloke/Mistral-7B-Instruct-v0.2-GGUF)")
       ap.add_argument("--hf-file", metavar="FILE", help="Filename in the HF repo")
       ap.add_argument("--hf-revision", metavar="REV", default="main", help="Hugging Face revision/branch (default: main)")
       ap.add_argument("--output", metavar="NAME", help="Output filename in models dir (default: from URL or --hf-file)")
       ap.add_argument("--force", action="store_true", help="Overwrite if file already exists")
       ap.add_argument("--list", action="store_true", help="List existing .gguf files in the models directory and exit")
       ap.add_argument("--models-dir", metavar="DIR", help="Override models directory (default: Thonny/Contour standard path)")
       args = ap.parse_args()

       models_dir = args.models_dir or get_models_dir()

       if args.list:
           if not os.path.isdir(models_dir):
               print(f"Models directory does not exist: {models_dir}")
               return 0
           names = sorted(f for f in os.listdir(models_dir) if f.lower().endswith(".gguf"))
           if not names:
               print(f"No .gguf files in {models_dir}")
               return 0
           print(f"Models in {models_dir}:")
           for n in names:
               path = os.path.join(models_dir, n)
               try:
                   size_mb = os.path.getsize(path) / (1024 * 1024)
                   print(f"  {n}  ({size_mb:.1f} MiB)")
               except OSError:
                   print(f"  {n}")
           return 0

       if args.url:
           url = args.url
           out_name = args.output or url.rstrip("/").split("/")[-1].split("?")[0]
       elif args.hf_repo and args.hf_file:
           url = hf_url(args.hf_repo, args.hf_file, args.hf_revision)
           out_name = args.output or args.hf_file
       else:
           ap.print_help()
           print("\nError: provide --url or both --hf-repo and --hf-file.", file=sys.stderr)
           return 1

       if not out_name.lower().endswith(".gguf"):
           out_name = out_name + ".gguf"
       dest_path = os.path.join(models_dir, out_name)

       download_file(url, dest_path, force=args.force)
       print(f"Set 'llama-cpp-python model path' in Contour to:\n  {dest_path}")
       return 0


   if __name__ == "__main__":
       sys.exit(main())


End users
---------
See https://thonny.org and `wiki <https://github.com/thonny/thonny/wiki>`_ for more info.


Contributors
------------
Contributions are welcome! See `CONTRIBUTING.rst <https://github.com/thonny/thonny/blob/master/CONTRIBUTING.rst>`_ for more info.


Sponsors
----------
You can sponsor development of Thonny by sending a donation to Thonny's main author Aivar Annamaa: https://github.com/thonny/thonny/wiki/Sponsors
