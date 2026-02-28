# -*- coding: utf-8 -*-
"""
Marimo notebook integration for Contour/Thonny.

Uses the Python version: marimo notebooks are plain .py files. Open them in the
editor and run with Run (F5); output appears in the shell. No browser.

- Left panel: "Marimo" tab with New notebook, Open notebook, Run notebook, Docs.
- Main window: "Marimo" view (optional) with short help.

Marimo: https://github.com/marimo-team/marimo
Docs: https://docs.marimo.io/guides/scripts/
"""

from __future__ import annotations

import os
from logging import getLogger
from tkinter import filedialog, messagebox, ttk

from thonny import get_workbench
from thonny.languages import tr
from thonny.ui_utils import ems_to_pixels

logger = getLogger(__name__)

MARIMO_DOCS_URL = "https://docs.marimo.io"
MARIMO_SCRIPTS_URL = "https://docs.marimo.io/guides/scripts/"
MARIMO_REPO_URL = "https://github.com/marimo-team/marimo"

# Minimal marimo notebook (runs as: python notebook.py)
MARIMO_TEMPLATE = '''import marimo as mo

__generated_with = "marimo"
app = mo.App()


@app.cell
def __():
    # Your code here. Run this file (F5) — output appears in the shell.
    x = 1
    print("Hello from marimo (Python script).")
    return (x,)


if __name__ == "__main__":
    app.run()
'''


def _marimo_available() -> bool:
    try:
        import marimo
        return True
    except ImportError:
        return False


def _create_new_notebook_file(cwd: str) -> str | None:
    """Create a new marimo .py file in cwd; return path or None if cancelled."""
    from tkinter import simpledialog

    base = simpledialog.askstring(
        tr("New marimo notebook"),
        tr("Filename (e.g. notebook.py):"),
        initialvalue="notebook.py",
        parent=get_workbench(),
    )
    if not base or not base.strip():
        return None
    name = base.strip()
    if not name.endswith(".py"):
        name += ".py"
    path = os.path.join(cwd, name)
    if os.path.exists(path):
        if not messagebox.askyesno(tr("Overwrite?"), tr("File exists. Overwrite?"), parent=get_workbench()):
            return None
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(MARIMO_TEMPLATE)
        return path
    except OSError as e:
        logger.exception("Failed to create %s", path)
        get_workbench().report_exception(e)
        return None


class MarimoJournalView(ttk.Frame):
    """Simple help view: marimo runs as Python script, output in shell."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        body = ttk.Frame(self, padding=ems_to_pixels(2))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=tr("Marimo (Python script)"), style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=(0, ems_to_pixels(0.5)))
        ttk.Label(
            body,
            text=tr("Marimo notebooks are plain .py files. Open one in the editor, then press Run (F5). Output appears in the shell below."),
            wraplength=ems_to_pixels(50),
        ).grid(row=1, column=0, sticky="w", pady=(0, ems_to_pixels(0.5)))
        ttk.Label(
            body,
            text=tr("Use the Marimo panel (left) to create or open a notebook."),
            wraplength=ems_to_pixels(50),
            style="Small.TLabel",
        ).grid(row=2, column=0, sticky="w")


class MarimoView(ttk.Frame):
    """Left-panel view: New notebook, Open notebook, Run notebook, Docs."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=ems_to_pixels(0.8), pady=(ems_to_pixels(0.5), 0))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=tr("Marimo"), style="Bold.TLabel").grid(row=0, column=0, sticky="w")
        self._status = ttk.Label(header, text="", style="Small.TLabel")
        self._status.grid(row=1, column=0, sticky="w")

        content = ttk.Frame(self, padding=ems_to_pixels(0.8))
        content.grid(row=1, column=0, sticky="nsew", padx=0, pady=(ems_to_pixels(0.3), 0))
        content.columnconfigure(0, weight=1)

        if _marimo_available():
            self._status.configure(text=tr("Run as Python script"))
            ttk.Label(
                content,
                text=tr("Notebooks are .py files. Run (F5) → output in shell."),
                wraplength=ems_to_pixels(18),
            ).grid(row=0, column=0, sticky="w", pady=(0, ems_to_pixels(0.5)))
            btn_new = ttk.Button(content, text=tr("New notebook"), command=self._on_new_notebook)
            btn_new.grid(row=1, column=0, sticky="ew", pady=2)
            btn_open = ttk.Button(content, text=tr("Open notebook…"), command=self._on_open_notebook)
            btn_open.grid(row=2, column=0, sticky="ew", pady=2)
            btn_run = ttk.Button(content, text=tr("Run notebook (F5)"), command=self._on_run_notebook)
            btn_run.grid(row=3, column=0, sticky="ew", pady=2)
            ttk.Separator(content, orient="horizontal").grid(row=4, column=0, sticky="ew", pady=ems_to_pixels(0.5))
            ttk.Label(content, text=tr("Docs"), style="Small.TLabel").grid(row=5, column=0, sticky="w", pady=(2, 0))
            link_scripts = ttk.Label(content, text=tr("Run as script"), style="Url.TLabel", cursor="hand2")
            link_scripts.grid(row=6, column=0, sticky="w")
            link_scripts.bind("<ButtonRelease-1>", lambda e: get_workbench().open_url(MARIMO_SCRIPTS_URL))
            link_docs = ttk.Label(content, text=MARIMO_DOCS_URL, style="Url.TLabel", cursor="hand2")
            link_docs.grid(row=7, column=0, sticky="w")
            link_docs.bind("<ButtonRelease-1>", lambda e: get_workbench().open_url(MARIMO_DOCS_URL))
        else:
            self._status.configure(text=tr("Not installed"))
            ttk.Label(
                content,
                text=tr("Marimo: reactive notebook stored as .py. Run as script."),
                wraplength=ems_to_pixels(18),
            ).grid(row=0, column=0, sticky="w", pady=(0, ems_to_pixels(0.5)))
            ttk.Label(
                content,
                text=tr("Install: pip install marimo"),
                wraplength=ems_to_pixels(18),
                style="Small.TLabel",
            ).grid(row=1, column=0, sticky="w", pady=(0, ems_to_pixels(0.5)))
            link_repo = ttk.Label(content, text=MARIMO_REPO_URL, style="Url.TLabel", cursor="hand2")
            link_repo.grid(row=2, column=0, sticky="w", pady=(0, ems_to_pixels(0.3)))
            link_repo.bind("<ButtonRelease-1>", lambda e: get_workbench().open_url(MARIMO_REPO_URL))
            link_docs = ttk.Label(content, text=tr("Docs") + ": " + MARIMO_DOCS_URL, style="Url.TLabel", cursor="hand2")
            link_docs.grid(row=3, column=0, sticky="w")
            link_docs.bind("<ButtonRelease-1>", lambda e: get_workbench().open_url(MARIMO_DOCS_URL))

    def _on_new_notebook(self) -> None:
        cwd = get_workbench().get_local_cwd()
        path = _create_new_notebook_file(cwd)
        if path:
            get_workbench().get_editor_notebook().show_file(path)

    def _on_open_notebook(self) -> None:
        cwd = get_workbench().get_local_cwd()
        path = filedialog.askopenfilename(
            parent=self,
            title=tr("Open marimo notebook"),
            initialdir=cwd,
            filetypes=[(tr("Python files") + " (.py)", "*.py"), (tr("All files"), "*")],
        )
        if path and os.path.isfile(path):
            get_workbench().get_editor_notebook().show_file(path)

    def _on_run_notebook(self) -> None:
        runner = get_workbench().get_runner()
        if runner and runner.cmd_run_current_script_enabled():
            runner.cmd_run_current_script()
        else:
            messagebox.showinfo(
                tr("Run notebook"),
                tr("Open a marimo .py file in the editor, then press Run (F5) or click Run notebook."),
                parent=get_workbench(),
            )


def load_plugin() -> None:
    wb = get_workbench()
    wb.add_view(
        MarimoView,
        tr("Marimo"),
        "nw",
        visible_by_default=True,
        default_position_key="MarimoView",
    )
    wb.add_view(
        MarimoJournalView,
        tr("Marimo notebook"),
        "s",
        visible_by_default=False,
        default_position_key="MarimoJournalView",
    )
