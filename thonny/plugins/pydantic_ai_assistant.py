# -*- coding: utf-8 -*-
"""
Pydantic AI–backed assistant for Thonny Chat.

Supports:
- Remote APIs (OpenAI, Anthropic, etc.) via HTTPS
- Local OpenAI-compatible servers (base URL)
- llama-cpp-python in-process: model is preloaded at app startup so chat is ready immediately

Runs in a background thread so the UI stays responsive; on Python 3.13+ with
free-threaded (no-GIL) build, the agent runs without holding the GIL.
"""

from __future__ import annotations

import os
import threading
from logging import getLogger
from tkinter import Toplevel, messagebox, ttk
from typing import Any, Iterator, List, Optional, Tuple

from thonny import get_thonny_user_dir
from thonny import get_workbench
from thonny.assistance import (
    Assistant,
    ChatContext,
    ChatMessage,
    ChatResponseChunk,
)
from thonny.config_ui import ConfigurationPage, add_option_combobox, add_option_entry
from thonny.languages import tr
from thonny.ui_utils import get_last_grid_row, show_dialog
from thonny.workdlg import WorkDialog

from thonny.plugins import llama_download

logger = getLogger(__name__)

# Config keys
BACKEND_OPTION = "pydantic_ai.backend"  # "api" | "local"
MODEL_OPTION = "pydantic_ai.model"  # e.g. "openai:gpt-4o" or model name for local
BASE_URL_OPTION = "pydantic_ai.base_url"  # for local / custom endpoint
LLAMA_MODEL_PATH_OPTION = "pydantic_ai.llama_model_path"  # path to .gguf for llama-cpp-python
LLAMA_CHAT_FORMAT_OPTION = "pydantic_ai.llama_chat_format"  # e.g. llama-2, chatml
LLAMA_N_CTX_OPTION = "pydantic_ai.llama_n_ctx"  # context window size (tokens) for llama-cpp-python
MAX_TOKENS_OPTION = "pydantic_ai.max_tokens"  # max response tokens (0 = provider default)
THINKING_OPTION = "pydantic_ai.thinking"  # optional scratchpad/thinking text appended to system
API_KEY_SECRET_KEY = "pydantic_ai_api_key"
INSTRUCTIONS_OPTION = "pydantic_ai.instructions"

# Preloaded llama-cpp-python model (set in background thread at startup)
_llama_instance: Any = None
_llama_load_error: Optional[str] = None
_llama_loading = threading.Lock()


def _is_probably_gguf(path: str) -> bool:
    return os.path.isfile(path) and path.lower().endswith(".gguf")


def _find_local_gguf_model() -> Optional[str]:
    """Try to locate a local GGUF model in common locations."""
    env_path = (
        os.environ.get("THONNY_LLAMA_MODEL", "")
        or os.environ.get("LLAMA_MODEL_PATH", "")
        or os.environ.get("LLAMA_CPP_MODEL", "")
    ).strip()
    if env_path and _is_probably_gguf(env_path):
        return env_path

    candidates: List[str] = []

    thonny_models_dir = os.path.join(get_thonny_user_dir(), "models")
    home = os.path.expanduser("~")

    common_dirs = [
        thonny_models_dir,
        os.path.join(home, "models"),
        os.path.join(home, "Models"),
        os.path.join(home, "Documents", "models"),
        os.path.join(home, "Documents", "Models"),
        os.path.join(home, "Downloads"),
        os.path.join(home, ".cache", "llama.cpp"),
        os.path.join(home, ".local", "share", "llama.cpp"),
        os.path.join(home, "Library", "Application Support", "llama.cpp"),
    ]

    for d in common_dirs:
        try:
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                path = os.path.join(d, name)
                if _is_probably_gguf(path):
                    candidates.append(path)
        except Exception:
            continue

    if not candidates:
        return None

    # Pick most recently modified model
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _ensure_local_model_configured() -> None:
    """
    Ensure there's a local model path when backend is local.
    If not configured, try to auto-detect one.
    """
    wb = get_workbench()
    backend = wb.get_option(BACKEND_OPTION, "api")
    base_url = (wb.get_option(BASE_URL_OPTION, "") or "").strip()
    existing = (wb.get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()

    # If user points to a server, don't guess a local file model.
    if base_url:
        return

    # If path is configured but missing, clear it so we can auto-detect.
    if existing and not os.path.isfile(existing):
        wb.set_option(LLAMA_MODEL_PATH_OPTION, "")
        existing = ""

    if existing:
        return

    # If they want local backend (or have no API configured), try to find a GGUF.
    api_key = wb.get_secret(API_KEY_SECRET_KEY, None)
    should_try = backend == "local" or (backend == "api" and not api_key)
    if not should_try:
        return

    found = _find_local_gguf_model()
    if found:
        wb.set_option(LLAMA_MODEL_PATH_OPTION, found)
        # If they don't have an API key, default to local so chat works immediately.
        if backend != "local" and not api_key:
            wb.set_option(BACKEND_OPTION, "local")


def _get_llama_model():
    """Return the preloaded llama-cpp-python Llama instance, or None if not available."""
    global _llama_instance, _llama_load_error
    with _llama_loading:
        return _llama_instance


def _preload_llama_model() -> None:
    """Load llama-cpp-python model in background so it's ready when the user opens chat."""
    global _llama_instance, _llama_load_error
    wb = get_workbench()
    path = (wb.get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()
    if not path or not os.path.isfile(path):
        return
    chat_format = (wb.get_option(LLAMA_CHAT_FORMAT_OPTION, "") or "llama-2").strip()
    n_ctx = wb.get_option(LLAMA_N_CTX_OPTION, 4096)
    try:
        n_ctx = int(n_ctx)
        if n_ctx < 512:
            n_ctx = 512
        elif n_ctx > 65536:
            n_ctx = 65536
    except (TypeError, ValueError):
        n_ctx = 4096
    try:
        from llama_cpp import Llama

        with _llama_loading:
            _llama_load_error = None
        logger.info("Preloading llama-cpp-python model: %s (n_ctx=%s)", path, n_ctx)
        llm = Llama(
            model_path=path,
            chat_format=chat_format or None,
            n_ctx=n_ctx,
            verbose=False,
        )
        with _llama_loading:
            _llama_instance = llm
            _llama_load_error = None
        logger.info("llama-cpp-python model loaded and ready.")
    except Exception as e:
        logger.exception("Failed to preload llama-cpp-python model")
        with _llama_loading:
            _llama_load_error = str(e)
            _llama_instance = None


def _start_llama_preload() -> None:
    """Kick off preload in a daemon thread so the app stays responsive."""
    t = threading.Thread(target=_preload_llama_model, daemon=True)
    t.start()


def _get_agent():
    """Build a pydantic_ai Agent from current options. Raises if pydantic_ai not installed."""
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as e:
        raise RuntimeError(
            "pydantic-ai is not installed. Install with: pip install pydantic-ai openai"
        ) from e

    backend = get_workbench().get_option(BACKEND_OPTION, "api")
    model_or_name = get_workbench().get_option(MODEL_OPTION, "openai:gpt-4o-mini")
    base_url = get_workbench().get_option(BASE_URL_OPTION, "").strip() or None
    instructions = _get_system_instructions() or (
        "You are a helpful programming coach. Be concise and clear."
    )
    api_key = get_workbench().get_secret(API_KEY_SECRET_KEY, None)

    # Custom endpoint (local llama.cpp server or custom API URL)
    if base_url:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",
        )
        model_name = model_or_name or "local"
        model = OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(openai_client=client),
        )
        return Agent(model, instructions=instructions)
    # Default: use model string (openai:gpt-4o, anthropic:claude-3-5-sonnet, etc.)
    return Agent(model_or_name, instructions=instructions)


def _get_max_tokens() -> int:
    """Return configured max_tokens (0 = use provider default)."""
    try:
        v = get_workbench().get_option(MAX_TOKENS_OPTION, 0)
        return int(v) if v else 0
    except (TypeError, ValueError):
        return 0


def _get_system_instructions() -> str:
    """System instructions plus optional thinking/scratchpad text."""
    instructions = get_workbench().get_option(INSTRUCTIONS_OPTION, "") or ""
    thinking = (get_workbench().get_option(THINKING_OPTION, "") or "").strip()
    if thinking:
        instructions = (instructions + "\n\n" + thinking).strip()
    return instructions


def _messages_to_llama_chat(context: ChatContext, assistant: Assistant) -> List[dict]:
    """Convert Thonny ChatContext to llama-cpp-python chat format."""
    instructions = _get_system_instructions()
    messages: List[dict] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    for msg in context.messages:
        content = assistant.format_message(msg) if msg.role == "user" else (msg.content or "")
        messages.append(
            {
                "role": msg.role if msg.role in ("user", "assistant", "system") else "user",
                "content": content,
            }
        )
    if getattr(context, "git_info", None) and messages and messages[-1].get("role") == "user":
        messages[-1][
            "content"
        ] = f"Current git context:\n{context.git_info}\n\n---\n\n{messages[-1]['content']}"
    return messages


class PydanticAIAssistant(Assistant):
    def get_ready(self) -> bool:
        backend = get_workbench().get_option(BACKEND_OPTION, "api")
        if backend == "api":
            api_key = get_workbench().get_secret(API_KEY_SECRET_KEY, None)
            if not api_key and not get_workbench().get_option(BASE_URL_OPTION, "").strip():
                show_dialog(PydanticAIConfigDialog(get_workbench()), get_workbench())
                api_key = get_workbench().get_secret(API_KEY_SECRET_KEY, None)
                if not api_key:
                    return False
        elif backend == "local":
            path = (get_workbench().get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()
            if path:
                llm = _get_llama_model()
                if llm is None and _llama_load_error:
                    messagebox.showerror(
                        tr("llama-cpp-python model failed to load"),
                        _llama_load_error,
                        parent=get_workbench(),
                    )
                    return False
                if llm is None:
                    # Still loading
                    messagebox.showinfo(
                        tr("Model loading"),
                        tr("Local model is still loading. Try again in a moment."),
                        parent=get_workbench(),
                    )
                    return False
                return True
            base_url = (get_workbench().get_option(BASE_URL_OPTION, "") or "").strip()
            if not base_url:
                messagebox.showerror(
                    tr("Local backend"),
                    tr(
                        "Set a model path (llama-cpp-python) or Base URL in Tools → Options → Pydantic AI."
                    ),
                    parent=get_workbench(),
                )
                return False
        try:
            _get_agent()
        except Exception as e:
            logger.exception("Pydantic AI agent setup failed")
            messagebox.showerror(
                tr("Pydantic AI"),
                str(e),
                parent=get_workbench(),
            )
            return False
        return True

    def complete_chat(self, context: ChatContext) -> Iterator[ChatResponseChunk]:
        if not context.messages:
            yield ChatResponseChunk("", is_final=True)
            return

        backend = get_workbench().get_option(BACKEND_OPTION, "api")
        llama_path = (get_workbench().get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()

        # Prefer llama-cpp-python in-process when backend is local and model path is set
        if backend == "local" and llama_path and os.path.isfile(llama_path):
            llm = _get_llama_model()
            if llm is not None:
                try:
                    messages = _messages_to_llama_chat(context, self)
                    max_tokens = _get_max_tokens()
                    stream = llm.create_chat_completion(
                        messages=messages,
                        stream=True,
                        max_tokens=max_tokens if max_tokens else 2048,
                    )
                    for chunk in stream:
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            yield ChatResponseChunk(content, is_final=False)
                    yield ChatResponseChunk("", is_final=True)
                except Exception as e:
                    logger.exception("llama-cpp-python chat failed")
                    yield ChatResponseChunk(
                        f"Error: {e}. See frontend.log for details.",
                        is_final=True,
                        is_interal_error=True,
                    )
                return
            if _llama_load_error:
                yield ChatResponseChunk(
                    f"Model failed to load: {_llama_load_error}",
                    is_final=True,
                    is_interal_error=True,
                )
                return
            yield ChatResponseChunk(
                tr("Model is still loading. Try again in a moment."),
                is_final=True,
                is_interal_error=True,
            )
            return

        # Pydantic AI path (API or local HTTP)
        try:
            agent = _get_agent()
        except Exception as e:
            yield ChatResponseChunk(
                f"Setup error: {e}. Install with: pip install pydantic-ai openai",
                is_final=True,
                is_interal_error=True,
            )
            return

        last_msg = context.messages[-1]
        user_content = self.format_message(last_msg)
        if getattr(context, "git_info", None):
            user_content = f"Current git context:\n{context.git_info}\n\n---\n\n{user_content}"
        message_history = None
        if len(context.messages) > 1:
            try:
                message_history = _build_message_history(
                    context.messages[:-1],
                    instructions=_get_system_instructions(),
                )
            except Exception as e:
                logger.debug("Could not build message history: %s", e)

        model_settings: dict = {}
        max_tokens = _get_max_tokens()
        if max_tokens > 0:
            model_settings["max_tokens"] = max_tokens
        try:
            with agent.run_stream_sync(
                user_content,
                message_history=message_history,
                model_settings=model_settings or None,
            ) as result:
                for chunk in result.stream_text():
                    if chunk:
                        yield ChatResponseChunk(chunk, is_final=False)
            yield ChatResponseChunk("", is_final=True)
        except Exception as e:
            logger.exception("Pydantic AI run failed")
            yield ChatResponseChunk(
                f"Error: {e}. Check your model and API key or base URL.",
                is_final=True,
                is_interal_error=True,
            )

    def cancel_completion(self) -> None:
        # Pydantic AI doesn't expose cancel from this thread; we rely on request_id
        pass


def _build_message_history(
    messages: List[ChatMessage],
    instructions: str = "",
) -> Optional[List]:
    """Build pydantic-ai message history from Thonny ChatMessage list."""
    try:
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            TextPart,
            UserPromptPart,
        )
    except ImportError:
        return None
    out: List = []
    try:
        for msg in messages:
            if msg.role == "user":
                out.append(
                    ModelRequest(
                        parts=[UserPromptPart(content=msg.content)],
                        instructions=instructions,
                    )
                )
            elif msg.role == "assistant" and msg.content:
                out.append(ModelResponse(parts=[TextPart(content=msg.content)]))
    except Exception as e:
        logger.debug("Building message history failed: %s", e)
        return None
    return out if out else None


class PydanticAIConfigDialog(WorkDialog):
    def __init__(self, master):
        self._saved = False
        super().__init__(master)

    def init_main_frame(self):
        super().init_main_frame()
        from tkinter import ttk

        ttk.Label(self.main_frame, text="API key (optional for local server):").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self._key_entry = ttk.Entry(self.main_frame, width=50, show="*")
        self._key_entry.grid(row=0, column=1, sticky="ew", pady=2, padx=5)
        current = get_workbench().get_secret(API_KEY_SECRET_KEY, "") or ""
        if current:
            self._key_entry.insert(0, current)
        self.main_frame.columnconfigure(1, weight=1)

    def is_ready_for_work(self):
        return True

    def on_click_ok_button(self):
        key = self._key_entry.get().strip() or None
        if key:
            get_workbench().set_secret(API_KEY_SECRET_KEY, key)
        self._saved = True
        self.close()


def _single_gguf_in_models_dir() -> Optional[str]:
    """If exactly one .gguf in the standard models dir, return its path; else None."""
    models_dir = llama_download.get_models_dir()
    if not os.path.isdir(models_dir):
        return None
    ggufs = [f for f in os.listdir(models_dir) if f.lower().endswith(".gguf")]
    if len(ggufs) != 1:
        return None
    return os.path.join(models_dir, ggufs[0])


class PydanticAIConfigPage(ConfigurationPage):
    def __init__(self, master):
        super().__init__(master)
        # Auto-fill path if empty and exactly one model in standard dir (no typing)
        if not (get_workbench().get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip():
            single = _single_gguf_in_models_dir()
            if single:
                get_workbench().set_option(LLAMA_MODEL_PATH_OPTION, single)
        add_option_combobox(
            self,
            BACKEND_OPTION,
            tr("Backend"),
            choices={
                tr("API (OpenAI, Anthropic, etc.)"): "api",
                tr("Local (e.g. llama.cpp server)"): "local",
            },
            width=28,
        )
        add_option_combobox(
            self,
            MODEL_OPTION,
            tr("API model"),
            choices={
                "openai:gpt-4o-mini": "openai:gpt-4o-mini",
                "openai:gpt-4o": "openai:gpt-4o",
                "openai:gpt-4o-small": "openai:gpt-4o-small",
                "anthropic:claude-3-5-sonnet": "anthropic:claude-3-5-sonnet",
                "anthropic:claude-3-haiku": "anthropic:claude-3-haiku",
            },
            width=36,
        )
        # Local model: dropdown of downloaded .gguf files only
        row = get_last_grid_row(self) + 1
        ttk.Label(self, text=tr("llama-cpp-python model path (.gguf; preloaded at startup)")).grid(
            row=row, column=0, sticky="w", pady=(0, 2)
        )
        self._downloaded_models: List[Tuple[str, str]] = []  # [(filename, full_path), ...]
        path_frame = ttk.Frame(self)
        path_frame.grid(row=row, column=1, sticky="ew", pady=(0, 2), padx=(5, 0))
        self._model_combobox = ttk.Combobox(path_frame, state="readonly", width=48)
        self._model_combobox.pack(side="left", fill="x", expand=True)
        self._model_combobox.bind("<<ComboboxSelected>>", self._on_model_selected)
        ttk.Button(
            path_frame, text=tr("Delete selected model"), command=self._on_delete_model
        ).pack(side="right", padx=(5, 0))
        self._refresh_downloaded_models()
        # Downloadable models: list of (display_name, hf_repo, hf_file)
        row = get_last_grid_row(self) + 1
        ttk.Label(self, text=tr("Download a model (GGUF):")).grid(
            row=row, column=0, sticky="w", pady=(8, 2)
        )
        self._downloadable: List[Tuple[str, str, str]] = llama_download.get_downloadable_models()
        download_frame = ttk.Frame(self)
        download_frame.grid(row=row, column=1, sticky="ew", pady=(8, 2), padx=(5, 0))
        self._download_combobox = ttk.Combobox(download_frame, state="readonly", width=52)
        self._download_combobox["values"] = [
            display_name for display_name, _repo, _file in self._downloadable
        ]
        self._download_combobox.pack(side="left", fill="x", expand=True)
        if self._downloadable:
            self._download_combobox.set(self._downloadable[0][0])
        ttk.Button(download_frame, text=tr("Download"), command=self._on_download_selected).pack(
            side="right", padx=(5, 0)
        )
        add_option_combobox(
            self,
            LLAMA_CHAT_FORMAT_OPTION,
            tr("Chat format (for llama-cpp-python)"),
            choices={
                "llama-2": "llama-2",
                "chatml": "chatml",
                "mistral": "mistral",
                "alpaca": "alpaca",
            },
            width=12,
        )
        add_option_entry(
            self,
            LLAMA_N_CTX_OPTION,
            tr("Context window size (tokens; llama-cpp-python, restart to apply)"),
            width=12,
        )
        add_option_entry(
            self,
            MAX_TOKENS_OPTION,
            tr("Max response tokens (0 = provider default)"),
            width=12,
        )
        add_option_entry(
            self,
            INSTRUCTIONS_OPTION,
            tr("System instructions"),
            width=50,
        )
        add_option_entry(
            self,
            BASE_URL_OPTION,
            tr("Base URL (local server only)"),
            width=40,
        )
        self.columnconfigure(1, weight=1)
        self.rowconfigure(get_last_grid_row(self), weight=1)

    def _refresh_downloaded_models(self) -> None:
        """Reload the list of .gguf files in the models dir and update the dropdown."""
        self._downloaded_models = llama_download.list_models()
        names = [name for name, _ in self._downloaded_models]
        if not names:
            names = [tr("(No models downloaded)")]
        self._model_combobox["values"] = names
        current = (get_workbench().get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()
        self._model_combobox.set(names[0] if names else "")
        for name, path in self._downloaded_models:
            if path == current:
                self._model_combobox.set(name)
                break

    def _on_model_selected(self, event: Any = None) -> None:
        """Set the model path option to the selected downloaded model."""
        sel = self._model_combobox.get()
        if not sel or sel == tr("(No models downloaded)"):
            return
        for name, path in self._downloaded_models:
            if name == sel:
                get_workbench().set_option(LLAMA_MODEL_PATH_OPTION, path)
                var = get_workbench().get_variable(LLAMA_MODEL_PATH_OPTION)
                if hasattr(var, "set"):
                    var.set(path)
                return

    def _on_delete_model(self) -> None:
        """Delete the currently selected model file (in models dir) after confirmation."""
        path = (get_workbench().get_option(LLAMA_MODEL_PATH_OPTION, "") or "").strip()
        if not path or not os.path.isfile(path):
            messagebox.showinfo(
                tr("Delete model"),
                tr("No model file selected or file not found."),
                parent=get_workbench(),
            )
            return
        if not messagebox.askyesno(
            tr("Delete model"),
            tr("Delete this model file from disk?\n\n%s") % path,
            parent=get_workbench(),
        ):
            return
        if not llama_download.delete_model(path):
            messagebox.showerror(
                tr("Delete model"),
                tr("Could not delete (file is not in the standard models folder)."),
                parent=get_workbench(),
            )
            return
        get_workbench().set_option(LLAMA_MODEL_PATH_OPTION, "")
        var = get_workbench().get_variable(LLAMA_MODEL_PATH_OPTION)
        if hasattr(var, "set"):
            var.set("")
        self._refresh_downloaded_models()
        messagebox.showinfo(
            tr("Delete model"),
            tr("Model deleted."),
            parent=get_workbench(),
        )

    def _on_download_selected(self) -> None:
        """Download the model selected in the 'Download a model' combobox."""
        sel = self._download_combobox.get()
        for display_name, hf_repo, hf_file in self._downloadable:
            if display_name == sel:
                self._run_download(hf_repo, hf_file)
                return
        messagebox.showinfo(
            tr("Download model"),
            tr("Select a model from the list first."),
            parent=get_workbench(),
        )

    def _run_download(self, hf_repo: str, hf_file: str) -> None:
        """Run a model download in a thread; show progress, then set path + backend and refresh list."""
        wb = get_workbench()
        config_page = self
        dlg = _DownloadProgressDialog(wb)
        result: List[Any] = []  # [path] or [None, error_msg]

        def run_download() -> None:
            try:

                def progress(pct: float, mb: float, total_mb: float) -> None:
                    wb.event_generate("<<LlamaDownloadProgress>>", when="tail")
                    dlg._last_pct, dlg._last_mb, dlg._last_total = pct, mb, total_mb

                path = llama_download.download_model(
                    hf_repo, hf_file, force=False, progress_callback=progress
                )
                result.append(path)
            except Exception as e:
                result.append(None)
                result.append(str(e))

        def on_progress(event=None) -> None:
            if hasattr(dlg, "_last_pct"):
                dlg._update_progress(dlg._last_pct, dlg._last_mb, dlg._last_total)

        def check_done() -> None:
            if not result:
                wb.after(200, check_done)
                return
            try:
                wb.unbind("<<LlamaDownloadProgress>>")
            except Exception:
                pass
            dlg.destroy()
            if result[0]:
                wb.set_option(LLAMA_MODEL_PATH_OPTION, result[0])
                wb.set_option(BACKEND_OPTION, "local")
                var = wb.get_variable(LLAMA_MODEL_PATH_OPTION)
                if hasattr(var, "set"):
                    var.set(result[0])
                try:
                    config_page._refresh_downloaded_models()
                except Exception:
                    pass
                messagebox.showinfo(
                    tr("Download complete"),
                    tr(
                        "Model installed. Restart Contour to load it, or use Chat now (may load in background)."
                    ),
                    parent=wb,
                )
            else:
                err = result[1] if len(result) > 1 else tr("Unknown error")
                if "SSL" in err or "CERTIFICATE" in err:
                    err = (
                        tr("SSL certificate verification failed.")
                        + "\n\n"
                        + tr(
                            'Reinstall Contour so certifi is installed: pip install -e ".[pydantic-ai,llama-cpp]" then restart.'
                        )
                        + " "
                        + tr(
                            'Or on macOS: Applications → Python 3.x → "Install Certificates.command".'
                        )
                        + "\n\n"
                        + tr("Original error:")
                        + " "
                        + err
                    )
                messagebox.showerror(tr("Download failed"), err, parent=wb)

        wb.bind("<<LlamaDownloadProgress>>", on_progress, add=True)
        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()
        wb.after(100, check_done)
        show_dialog(dlg._win, wb)


class _DownloadProgressDialog:
    """Shown while the recommended GGUF model is downloading. No buttons; closes when done."""

    def __init__(self, master):
        self._last_pct = 0.0
        self._last_mb = 0.0
        self._last_total = 0.0
        self._win = Toplevel(master)
        self._win.title(tr("Downloading model"))
        self._frame = ttk.Frame(self._win, padding=10)
        self._frame.pack(fill="both", expand=True)
        self._label = ttk.Label(
            self._frame,
            text=tr("Downloading recommended model (~0.7 GB)..."),
        )
        self._label.grid(row=0, column=0, sticky="w", pady=5)
        self._progress = ttk.Label(self._frame, text="0.0%")
        self._progress.grid(row=1, column=0, sticky="w", pady=2)
        self._win.transient(master)
        self._win.grab_set()

    def _update_progress(self, pct: float, mb: float, total_mb: float) -> None:
        self._progress["text"] = f"{pct:.1f}% ({mb:.1f} / {total_mb:.1f} MiB)"

    def destroy(self) -> None:
        try:
            self._win.grab_release()
        except Exception:
            pass
        try:
            self._win.destroy()
        except Exception:
            pass


def load_plugin():
    wb = get_workbench()
    wb.set_default(BACKEND_OPTION, "api")
    wb.set_default(MODEL_OPTION, "openai:gpt-4o-mini")
    wb.set_default(BASE_URL_OPTION, "")
    wb.set_default(LLAMA_MODEL_PATH_OPTION, "")
    wb.set_default(LLAMA_CHAT_FORMAT_OPTION, "llama-2")
    wb.set_default(LLAMA_N_CTX_OPTION, 4096)
    wb.set_default(MAX_TOKENS_OPTION, 0)
    wb.set_default(THINKING_OPTION, "")
    wb.set_default(
        INSTRUCTIONS_OPTION,
        "You are a helpful programming coach. Be concise and clear.",
    )
    wb.add_assistant("PydanticAI", PydanticAIAssistant())
    wb.add_configuration_page(
        "pydantic_ai",
        tr("Pydantic AI"),
        PydanticAIConfigPage,
        75,
    )

    def _cmd_change_ai_model():
        wb.show_options("pydantic_ai")

    wb.add_command(
        "change_ai_model",
        "tools",
        tr("Change AI / local model..."),
        _cmd_change_ai_model,
        group=179,
    )

    # Auto-detect a local GGUF model and preload at startup so chat is ready immediately.
    def _on_workbench_ready(event=None):
        _ensure_local_model_configured()
        _start_llama_preload()

    wb.bind("WorkbenchReady", _on_workbench_ready, True)
