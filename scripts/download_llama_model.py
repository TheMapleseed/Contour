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

Recommended small model for Metal / low RAM (Apple Silicon friendly, ~0.7 GB):
  python3 scripts/download_llama_model.py --hf-repo TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF --hf-file tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

Usage:
  python3 scripts/download_llama_model.py --url "https://example.com/model.Q4_K_M.gguf"
  python3 scripts/download_llama_model.py --hf-repo REPO --hf-file FILE.gguf
  python3 scripts/download_llama_model.py --list

Models directory (same on all OSes):
  - THONNY_USER_DIR/models if THONNY_USER_DIR is set
  - Windows: %%APPDATA%%\\Thonny\\models
  - macOS: ~/Library/Thonny/models
  - Linux: $XDG_CONFIG_HOME/Thonny/models (default ~/.config/Thonny/models)

Contour's AI plugin auto-detects .gguf files in this directory. If you get
SSL errors on macOS, run: /Applications/Python 3.x/Install Certificates.command
"""

from __future__ import annotations

import argparse
import os
import ssl
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


def _ssl_context():
    """Use certifi CA bundle so HTTPS works on macOS when system certs are missing."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def download_file(url: str, dest_path: str, force: bool = False) -> bool:
    """Download url to dest_path. Return True if downloaded, False if skipped (exists and not force)."""
    if os.path.isfile(dest_path) and not force:
        print(f"Already exists (use --force to replace): {dest_path}")
        return False
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"Downloading {url}")
    print(f"  -> {dest_path}")
    req = urllib.request.Request(url, headers={"User-Agent": "Contour-LLM-Download/1.0"})
    ctx = _ssl_context()
    try:
        resp = urllib.request.urlopen(req, context=ctx) if ctx else urllib.request.urlopen(req)
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
    ap.add_argument(
        "--url",
        metavar="URL",
        help="Direct URL to a .gguf file",
    )
    ap.add_argument(
        "--hf-repo",
        metavar="REPO",
        help="Hugging Face repo (e.g. TheBloke/Mistral-7B-Instruct-v0.2-GGUF)",
    )
    ap.add_argument(
        "--hf-file",
        metavar="FILE",
        help="Filename in the HF repo (e.g. mistral-7b-instruct-v0.2.Q4_K_M.gguf)",
    )
    ap.add_argument(
        "--hf-revision",
        metavar="REV",
        default="main",
        help="Hugging Face revision/branch (default: main)",
    )
    ap.add_argument(
        "--output",
        metavar="NAME",
        help="Output filename in models dir (default: from URL or --hf-file)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite if file already exists",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="List existing .gguf files in the models directory and exit",
    )
    ap.add_argument(
        "--models-dir",
        metavar="DIR",
        help="Override models directory (default: Thonny/Contour standard path)",
    )
    args = ap.parse_args()

    models_dir = args.models_dir
    if not models_dir:
        models_dir = get_models_dir()

    if args.list:
        if not os.path.isdir(models_dir):
            print(f"Models directory does not exist: {models_dir}")
            return 0
        names = sorted(
            f for f in os.listdir(models_dir)
            if f.lower().endswith(".gguf")
        )
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
