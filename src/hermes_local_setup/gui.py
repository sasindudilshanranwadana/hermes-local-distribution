"""Tk-based novice setup wizard packaged as a standalone desktop executable."""

from __future__ import annotations

import os
import platform
import shutil
import threading
import tkinter as tk
import tomllib
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .capabilities import bind_capabilities, infer_model_candidate
from .installer import Installer
from .models import InstallAnswers, InstallMode, ProviderConfig, ProviderKind
from .paths import resolve_layout
from .resources import resource_root
from .wizard import WizardPage, WizardState


class SetupWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Hermes Local System Setup")
        self.geometry("820x610")
        self.minsize(760, 560)
        self.state_model = WizardState()
        self.install_mode = tk.StringVar(value=InstallMode.HYBRID.value)
        self.enable_mem0 = tk.BooleanVar(value=True)
        self.provider_choice = tk.StringVar(value="openrouter")
        self.endpoint = tk.StringVar()
        self.credential = tk.StringVar()
        self.model_id = tk.StringVar()
        self.context_window = tk.StringVar(value="128000")
        self.status = tk.StringVar(value="Ready")
        self.providers: list[ProviderConfig] = []
        self.models = []
        self.credentials: dict[str, str] = {}
        self.provider_catalog = self._load_provider_catalog()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, padding=(24, 18, 24, 8))
        header.grid(row=0, column=0, sticky="ew")
        self.title_label = ttk.Label(header, font=("TkDefaultFont", 18, "bold"))
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(header, foreground="#555555")
        self.subtitle_label.pack(anchor="w", pady=(4, 0))

        self.content = ttk.Frame(self, padding=24)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        footer = ttk.Frame(self, padding=(24, 10, 24, 18))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        self.next_button = ttk.Button(footer, text="Continue", command=self._next)
        self.next_button.pack(side="right")
        self.back_button = ttk.Button(footer, text="Back", command=self._back)
        self.back_button.pack(side="right", padx=(0, 10))
        self._render()

    def _load_provider_catalog(self) -> dict[str, dict[str, Any]]:
        path = resource_root() / "manifests" / "providers.toml"
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        return {entry["id"]: entry for entry in payload.get("provider", [])}

    def _clear(self) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()

    def _render(self) -> None:
        self._clear()
        page = self.state_model.page
        self.title_label.configure(text=page.value)
        self.subtitle_label.configure(text=f"Step {self.state_model.index + 1} of 10")
        self.back_button.configure(state="normal" if self.state_model.can_go_back else "disabled")
        self.next_button.configure(text="Finish" if page is WizardPage.FINISH else "Continue")
        renderers = {
            WizardPage.WELCOME: self._welcome,
            WizardPage.PRIVACY: self._privacy,
            WizardPage.SYSTEM_CHECK: self._system_check,
            WizardPage.MODE: self._mode,
            WizardPage.PROVIDERS: self._providers,
            WizardPage.OPTIONS: self._options,
            WizardPage.REVIEW: self._review,
            WizardPage.INSTALL: self._install,
            WizardPage.VERIFY: self._verify,
            WizardPage.FINISH: self._finish,
        }
        renderers[page]()

    def _label(self, text: str) -> None:
        ttk.Label(self.content, text=text, wraplength=700, justify="left").grid(
            row=0, column=0, sticky="nw"
        )

    def _welcome(self) -> None:
        self._label(
            "This installer sets up Hermes Desktop with the routing, memory, verification, "
            "and safety configuration prepared for this distribution. You will only need to "
            "choose where models run and provide credentials for services you own."
        )

    def _privacy(self) -> None:
        self._label(
            "Your credentials, conversations, files, and memories remain on this computer. "
            "Cloud providers receive prompts only when you choose a cloud or hybrid mode. "
            "Nothing connects to the system author's server."
        )

    def _system_check(self) -> None:
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nw")
        checks = (
            ("Docker Desktop", shutil.which("docker") is not None),
            ("Hermes Agent", shutil.which("hermes") is not None),
        )
        for row, (name, available) in enumerate(checks):
            icon = "Ready" if available else "Will be installed / needs attention"
            ttk.Label(frame, text=f"{name}: {icon}").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Label(
            frame,
            text="Docker Desktop must be installed and running before local services can start.",
            foreground="#555555",
        ).grid(row=len(checks), column=0, sticky="w", pady=(18, 0))

    def _mode(self) -> None:
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nw")
        choices = (
            (InstallMode.HYBRID, "Hybrid (recommended)", "Use local and cloud models."),
            (InstallMode.CLOUD, "Cloud providers", "Simplest on ordinary laptops."),
            (InstallMode.LOCAL, "Fully local", "No cloud inference; requires a capable computer."),
        )
        for row, (mode, title, detail) in enumerate(choices):
            ttk.Radiobutton(
                frame, text=title, value=mode.value, variable=self.install_mode
            ).grid(row=row * 2, column=0, sticky="w", pady=(8, 0))
            ttk.Label(frame, text=detail, foreground="#555555").grid(
                row=row * 2 + 1, column=0, sticky="w", padx=(24, 0)
            )

    def _providers(self) -> None:
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Provider").grid(row=0, column=0, sticky="w", padx=(0, 10))
        combo = ttk.Combobox(
            frame,
            textvariable=self.provider_choice,
            values=tuple(self.provider_catalog),
            state="readonly",
        )
        combo.grid(row=0, column=1, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._fill_provider_defaults())
        ttk.Label(frame, text="Endpoint").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.endpoint).grid(row=1, column=1, sticky="ew", pady=8)
        ttk.Label(frame, text="API key (if required)").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.credential, show="•").grid(
            row=2, column=1, sticky="ew", pady=8
        )
        ttk.Label(frame, text="Model name").grid(row=3, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.model_id).grid(row=3, column=1, sticky="ew", pady=8)
        ttk.Label(frame, text="Context size").grid(row=4, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.context_window).grid(
            row=4, column=1, sticky="ew", pady=8
        )
        ttk.Button(frame, text="Add provider", command=self._add_provider).grid(
            row=5, column=1, sticky="e", pady=(10, 16)
        )
        self.provider_list = tk.Listbox(frame, height=6)
        self.provider_list.grid(row=6, column=0, columnspan=2, sticky="ew")
        for provider, model in zip(self.providers, self.models, strict=True):
            self.provider_list.insert("end", f"{provider.provider_id}: {model.model_id}")
        self._fill_provider_defaults(only_if_empty=True)

    def _fill_provider_defaults(self, only_if_empty: bool = False) -> None:
        entry = self.provider_catalog.get(self.provider_choice.get())
        if not entry:
            return
        if not only_if_empty or not self.endpoint.get():
            self.endpoint.set(str(entry["base_url"]))

    def _add_provider(self) -> None:
        try:
            definition = self.provider_catalog[self.provider_choice.get()]
            privacy = "local" if definition["kind"] in {"ollama", "lm-studio"} else "cloud"
            provider = ProviderConfig(
                provider_id=str(definition["id"]),
                kind=ProviderKind(str(definition["kind"])),
                base_url=self.endpoint.get().strip(),
                credential_env=definition.get("credential_env"),
                privacy=privacy,
            )
            model_id = self.model_id.get().strip()
            if not model_id:
                raise ValueError("Enter the model name shown by your provider")
            model = infer_model_candidate(
                provider_id=provider.provider_id,
                model_id=model_id,
                context_window=int(self.context_window.get()),
            )
            if provider.credential_env:
                key = self.credential.get().strip()
                if not key:
                    raise ValueError("This provider requires an API key")
                self.credentials[provider.credential_env] = key
            self.providers.append(provider)
            self.models.append(model)
            self.credential.set("")
            self.model_id.set("")
            self.provider_list.insert("end", f"{provider.provider_id}: {model.model_id}")
            self.status.set(f"Added {provider.provider_id}")
        except (KeyError, ValueError) as error:
            messagebox.showerror("Provider could not be added", str(error), parent=self)

    def _options(self) -> None:
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nw")
        ttk.Checkbutton(
            frame,
            text="Enable self-hosted Mem0 long-term memory",
            variable=self.enable_mem0,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Mem0 starts empty. No memories from another installation are included.",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", padx=(24, 0), pady=(5, 0))

    def _review(self) -> None:
        mode = self.install_mode.get()
        provider_text = ", ".join(provider.provider_id for provider in self.providers) or "None"
        self._label(
            f"Mode: {mode}\nProviders: {provider_text}\n"
            f"Self-hosted memory: {'Enabled' if self.enable_mem0.get() else 'Built-in only'}\n\n"
            "Continue to install. Existing memories and unrelated settings will be preserved."
        )

    def _install(self) -> None:
        frame = ttk.Frame(self.content)
        frame.grid(row=0, column=0, sticky="nw")
        ttk.Label(frame, text="Ready to install the local system.").grid(row=0, column=0, sticky="w")
        ttk.Button(frame, text="Install now", command=self._start_install).grid(
            row=1, column=0, sticky="w", pady=20
        )

    def _start_install(self) -> None:
        if not self.providers:
            messagebox.showerror("Provider required", "Add at least one model provider.", parent=self)
            return
        self.next_button.configure(state="disabled")
        self.back_button.configure(state="disabled")
        self.status.set("Installing… this can take several minutes")

        def work() -> None:
            try:
                answers = InstallAnswers(
                    mode=InstallMode(self.install_mode.get()),
                    providers=tuple(self.providers),
                    enable_mem0=self.enable_mem0.get(),
                )
                layout = resolve_layout(
                    platform_name=platform.system(), home=Path.home(), environ=os.environ
                )
                Installer(dry_run=False, install_optional_components=True).install(
                    answers=answers,
                    binding=bind_capabilities(tuple(self.models)),
                    layout=layout,
                    credentials=self.credentials,
                )
                self.after(0, self._install_complete)
            except Exception as error:  # GUI boundary reports a safe, concise failure.
                self.after(0, lambda: self._install_failed(str(error)))

        threading.Thread(target=work, daemon=True).start()

    def _install_complete(self) -> None:
        self.credentials.clear()
        self.credential.set("")
        self.status.set("Installation completed")
        self.next_button.configure(state="normal")
        self.state_model = WizardState(8)
        self._render()

    def _install_failed(self, message: str) -> None:
        self.status.set("Installation needs attention")
        self.next_button.configure(state="normal")
        self.back_button.configure(state="normal")
        messagebox.showerror("Installation stopped", message, parent=self)

    def _verify(self) -> None:
        self._label(
            "The installer verified the service stack and Hermes configuration. Use the Doctor "
            "command from this setup tool if anything later needs repair."
        )

    def _finish(self) -> None:
        self._label("Hermes is ready. Close this window and open Hermes Desktop to begin.")

    def _next(self) -> None:
        if self.state_model.page is WizardPage.FINISH:
            self.destroy()
            return
        if self.state_model.page is WizardPage.PROVIDERS and not self.providers:
            messagebox.showerror("Provider required", "Add at least one provider.", parent=self)
            return
        self.state_model = self.state_model.advance()
        self._render()

    def _back(self) -> None:
        self.state_model = self.state_model.back()
        self._render()


def launch() -> None:
    SetupWizard().mainloop()
