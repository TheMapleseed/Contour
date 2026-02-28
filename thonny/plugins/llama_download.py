# -*- coding: utf-8 -*-
"""
One-click download of GGUF models into Thonny/Contour models dir.
Used by the Pydantic AI config page and by scripts/download_llama_model.py (CLI).
"""

from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request
from typing import List, Tuple

from thonny import get_thonny_user_dir


def _ssl_context() -> ssl.SSLContext | None:
    """Use certifi's CA bundle so HTTPS works on macOS and other systems without system certs."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None

# Curated list of downloadable GGUF models: (display_name, hf_repo, hf_file)
# Display name is shown in the UI; repo/file are used for Hugging Face download.
DOWNLOADABLE_GGUF_MODELS: List[Tuple[str, str, str]] = [
    ("TinyLlama 1.1B Chat (Q4_K_M, ~0.7 GB)", "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"),
    ("Phi-2 (Q4_K_M, ~1.6 GB)", "TheBloke/phi-2-GGUF", "phi-2.Q4_K_M.gguf"),
    ("Qwen2 0.5B Instruct (Q4_K_M, ~0.4 GB)", "Qwen/Qwen2-0.5B-Instruct-GGUF", "qwen2-0.5b-instruct-q4_k_m.gguf"),
    ("SmolLM2 360M Instruct (Q4_K_M, ~0.3 GB)", "HuggingFaceTB/SmolLM2-360M-Instruct-GGUF", "smollm2-360m-instruct-q4_k_m.gguf"),
    ("Mistral 7B Instruct v0.2 (Q4_K_M, ~4.1 GB)", "TheBloke/Mistral-7B-Instruct-v0.2-GGUF", "mistral-7b-instruct-v0.2.Q4_K_M.gguf"),
    ("Llama 3.2 1B Instruct (Q4_K_M, ~0.8 GB)", "bartowski/Llama-3.2-1B-Instruct-GGUF", "Llama-3.2-1B-Instruct-Q4_K_M.gguf"),
    ("Llama 3.2 3B Instruct (Q4_K_M, ~2 GB)", "bartowski/Llama-3.2-3B-Instruct-GGUF", "Llama-3.2-3B-Instruct-Q4_K_M.gguf"),
]

RECOMMENDED_HF_REPO = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
RECOMMENDED_HF_FILE = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"


def get_downloadable_models() -> List[Tuple[str, str, str]]:
    """Return list of (display_name, hf_repo, hf_file) for models that can be downloaded."""
    return list(DOWNLOADABLE_GGUF_MODELS)


def get_models_dir() -> str:
    """Same models directory Contour/Thonny uses on all OSes."""
    return os.path.join(get_thonny_user_dir(), "models")


def list_models() -> List[Tuple[str, str]]:
    """List .gguf files in the models dir. Returns [(filename, full_path), ...] sorted by name."""
    models_dir = get_models_dir()
    if not os.path.isdir(models_dir):
        return []
    out: List[Tuple[str, str]] = []
    for name in sorted(os.listdir(models_dir)):
        if name.lower().endswith(".gguf"):
            out.append((name, os.path.join(models_dir, name)))
    return out


def delete_model(path: str) -> bool:
    """Delete a .gguf file if it is inside the standard models dir. Returns True if deleted."""
    models_dir = get_models_dir()
    path = os.path.normpath(os.path.abspath(path))
    models_dir_abs = os.path.normpath(os.path.abspath(models_dir))
    if not path.startswith(models_dir_abs + os.sep) and path != models_dir_abs:
        return False
    if not path.lower().endswith(".gguf"):
        return False
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def _hf_url(repo: str, filename: str, revision: str = "main") -> str:
    repo = repo.strip().strip("/")
    if "/" in repo:
        org, name = repo.split("/", 1)
    else:
        org, name = repo, repo
    return f"https://huggingface.co/{org}/{name}/resolve/{revision}/{filename}"


def download_file(
    url: str,
    dest_path: str,
    force: bool = False,
    progress_callback=None,
) -> bool:
    """Download url to dest_path. progress_callback(percent, size_mb, total_mb) if given."""
    if os.path.isfile(dest_path) and not force:
        return False
    dest_dir = os.path.dirname(dest_path)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Contour-LLM-Download/1.0"})
    ctx = _ssl_context()
    try:
        resp = urllib.request.urlopen(req, context=ctx) if ctx else urllib.request.urlopen(req)
    except urllib.error.URLError:
        raise
    with resp:
        total = resp.headers.get("Content-Length")
        total = int(total) if total else None
        size = 0
        chunk_size = 1024 * 1024
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
                if progress_callback and total and total > 0:
                    pct = min(100.0, 100 * size / total)
                    mb = size / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    progress_callback(pct, mb, total_mb)
    return True


def download_recommended_model(
    force: bool = False,
    progress_callback=None,
) -> str | None:
    """
    Download the recommended small model (TinyLlama 1.1B, ~0.7 GB) into the models dir.
    Returns the path to the .gguf file on success, None if already exists (and not force).
    Raises on network/SSL errors.
    """
    return download_model(RECOMMENDED_HF_REPO, RECOMMENDED_HF_FILE, force=force, progress_callback=progress_callback)


def download_model(
    hf_repo: str,
    hf_file: str,
    force: bool = False,
    progress_callback=None,
    output_filename: str | None = None,
) -> str | None:
    """
    Download a GGUF model from Hugging Face into the models dir.
    Returns the path to the .gguf file on success; None if file already exists and not force.
    Raises on network/SSL errors.
    """
    models_dir = get_models_dir()
    filename = output_filename or hf_file
    if not filename.lower().endswith(".gguf"):
        filename = filename + ".gguf"
    dest_path = os.path.join(models_dir, filename)
    if os.path.isfile(dest_path) and not force:
        return dest_path
    url = _hf_url(hf_repo, hf_file)
    download_file(url, dest_path, force=force, progress_callback=progress_callback)
    return dest_path
