"""Textual-based CLI UI for apimon."""

import asyncio
import os
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    TabbedContent,
    TabPane,
    Log,
    Button,
    Input,
    Label,
    Select,
    LoadingIndicator,
)
from textual.reactive import reactive

from apimon.storage import DataStore
from apimon.analytics import AnalyticsEngine
from apimon.llm import (
    LLMProvider,
    LLMClient,
    try_create_llm_client,
    format_analytics_prompt,
    get_provider_choices,
)

_PROVIDER_OPTIONS = [(p.value.capitalize(), p.value) for p in LLMProvider]

_ENV_KEYS = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.GEMINI: "GEMINI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
}


class SetupScreen(ModalScreen[tuple[Optional[LLMClient], bool]]):
    """Modal screen to collect LLM provider and API key at startup."""

    CSS = """
    SetupScreen {
        align: center middle;
    }
    #setup-dialog {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #setup-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #setup-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    .setup-label {
        margin-top: 1;
        color: $text;
    }
    #provider-select {
        margin-bottom: 1;
    }
    #api-key-input {
        margin-bottom: 1;
    }
    #env-hint {
        color: $success;
        margin-bottom: 1;
    }
    #setup-buttons {
        margin-top: 1;
        height: 3;
        align: center middle;
    }
    #btn-confirm {
        margin-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="setup-dialog"):
            yield Static("🤖  LLM Insights Setup", id="setup-title")
            yield Static(
                "Enter an API key to enable AI-powered insights inside the dashboard.\n"
                "Press [bold]Skip[/bold] to launch without LLM support.",
                id="setup-hint",
            )
            yield Label("Provider", classes="setup-label")
            yield Select(
                options=_PROVIDER_OPTIONS,
                value="openai",
                id="provider-select",
            )
            yield Label("API Key", classes="setup-label")
            yield Input(placeholder="Paste your API key here (or leave blank)", password=True, id="api-key-input")
            yield Static("", id="env-hint")
            with Horizontal(id="setup-buttons"):
                yield Button("Confirm", variant="primary", id="btn-confirm")
                yield Button("Skip", variant="default", id="btn-skip")

    def on_mount(self) -> None:
        self._update_env_hint()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._update_env_hint()

    def _update_env_hint(self) -> None:
        hint = self.query_one("#env-hint", Static)
        provider_val = self.query_one("#provider-select", Select).value
        if provider_val is Select.BLANK:
            hint.update("")
            return
        try:
            provider = LLMProvider(provider_val)
            env_var = _ENV_KEYS.get(provider, "")
            if env_var and os.environ.get(env_var):
                hint.update(f"✓ {env_var} is already set in environment")
            elif env_var:
                hint.update(f"Tip: set {env_var} in environment to skip this step next time")
        except ValueError:
            hint.update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-skip":
            self.dismiss((None, False))
            return

        provider_val = self.query_one("#provider-select", Select).value
        raw_key = self.query_one("#api-key-input", Input).value.strip()

        if provider_val is Select.BLANK:
            self.dismiss((None, False))
            return

        try:
            provider = LLMProvider(str(provider_val))
        except ValueError:
            self.dismiss((None, False))
            return

        api_key = raw_key or None
        client = try_create_llm_client(provider, api_key)
        self.dismiss((client, True))


class DashboardScreen(App):
    """Main dashboard screen for apimon Textual UI."""

    CSS = """
    Screen {
        background: $surface;
    }
    #stats-panel {
        height: 3;
        background: $panel;
        dock: top;
        content-align: center middle;
    }
    #stats-panel Static {
        text-style: bold;
        color: $accent;
    }
    #routes-table {
        height: 1fr;
    }
    #requests-table {
        height: 1fr;
    }
    #analytics-scroll {
        height: 1fr;
    }
    #analytics-content {
        padding: 0 1;
    }
    #llm-section {
        height: auto;
        border-top: solid $panel;
        padding: 1 1 0 1;
    }
    #llm-controls {
        height: 3;
        align: left middle;
    }
    #btn-llm {
        margin-right: 2;
    }
    #llm-status {
        color: $text-muted;
    }
    #llm-output {
        padding: 1;
        color: $text;
        min-height: 3;
    }
    #llm-loading {
        height: 3;
        display: none;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("1", "switch_tab('routes')", "Routes", show=True),
        Binding("2", "switch_tab('requests')", "Requests", show=True),
        Binding("3", "switch_tab('analytics')", "Analytics", show=True),
        Binding("d", "toggle_dark", "Toggle Dark", show=True),
    ]

    db_path: str = "apimon.db"
    _store: Optional[DataStore] = None
    _analytics: Optional[AnalyticsEngine] = None
    _llm_client: Optional[LLMClient] = None

    def __init__(self, db_path: str = "apimon.db", **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path

    @property
    def store(self) -> DataStore:
        if self._store is None:
            self._store = DataStore(self.db_path)
        return self._store

    @property
    def analytics(self) -> AnalyticsEngine:
        if self._analytics is None:
            self._analytics = AnalyticsEngine(self.store)
        return self._analytics

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static("🚀 apimon - API Monitor Dashboard", id="title"),
            id="stats-panel",
        )
        with TabbedContent(initial="routes"):
            with TabPane("Routes", id="routes"):
                yield DataTable(id="routes-table")
            with TabPane("Requests", id="requests"):
                yield DataTable(id="requests-table")
            with TabPane("Analytics", id="analytics"):
                with ScrollableContainer(id="analytics-scroll"):
                    yield Static("", id="analytics-content")
                    with Container(id="llm-section"):
                        with Horizontal(id="llm-controls"):
                            yield Button("✨ Get LLM Insights", variant="primary", id="btn-llm")
                            yield Static("", id="llm-status")
                        yield LoadingIndicator(id="llm-loading")
                        yield Static("", id="llm-output")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "apimon - API Monitor"
        self.sub_title = "Textual UI"
        self.push_screen(SetupScreen(), self._on_setup_done)

    def _on_setup_done(self, result: tuple[Optional[LLMClient], bool]) -> None:
        client, confirmed = result
        self._llm_client = client
        status = self.query_one("#llm-status", Static)
        btn = self.query_one("#btn-llm", Button)
        if client is not None:
            status.update(f"[green]✓ LLM ready ({client.provider.value})[/green]")
        elif confirmed:
            status.update("[red]✗ Could not initialise LLM client – check your key[/red]")
            btn.disabled = True
        else:
            status.update("[yellow]No LLM configured (skipped)[/yellow]")
            btn.disabled = True
        self.refresh_data()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh(self) -> None:
        self.refresh_data()

    def action_toggle_dark(self) -> None:
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def refresh_data(self):
        self.refresh_routes()
        self.refresh_requests()
        self.refresh_analytics()

    def refresh_routes(self):
        """Refresh routes table."""
        table = self.query_one("#routes-table", DataTable)
        table.clear()

        stats = self.store.get_route_stats()
        if stats:
            if not table.columns:
                table.add_columns("Method", "Route", "Hits", "Avg ms", "Errors %")
            for route in stats[:20]:
                table.add_row(
                    route["method"],
                    route["route_pattern"][:50],
                    str(route["hit_count"]),
                    f"{route['avg_response_time_ms']:.1f}",
                    f"{route['error_rate']:.1f}%",
                )

    def refresh_requests(self):
        """Refresh requests table."""
        table = self.query_one("#requests-table", DataTable)
        table.clear()

        requests = self.store.get_recent_requests(limit=50)
        if requests:
            if not table.columns:
                table.add_columns("ID", "Method", "Path", "Status", "Time ms")
            for req in requests:
                table.add_row(
                    str(req["id"]),
                    req["method"],
                    req["path"][:40],
                    str(req["response_status"]),
                    f"{req['response_time_ms']:.1f}",
                )

    def refresh_analytics(self):
        """Refresh analytics display."""
        content = self.query_one("#analytics-content", Static)
        analytics_data = self.store.get_analytics_summary()
        suggestions = self.analytics.generate_suggestions()

        graph_data = self.analytics.get_graph_data(hours=1)
        graph = self.analytics.render_ascii_graph(graph_data.get("time_series", [])[:10])

        text = f"""[bold]Analytics Summary[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Requests:  {analytics_data['total_requests']}
Error Rate:      {analytics_data['error_rate']:.1f}%
Avg Response:    {analytics_data['avg_response_time_ms']:.0f}ms
Unique Routes:   {analytics_data['unique_routes']}

[bold]Time Series (last hour)[/bold]
{graph}

[bold]Rule-based Suggestions[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        for s in suggestions[:5]:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "⚪")
            text += f"\n{emoji} [{s.severity.upper()}] {s.message}"

        content.update(text)

    async def _run_llm_insights(self) -> None:
        """Run LLM insights call in background and update the output widget."""
        if self._llm_client is None:
            return

        loading = self.query_one("#llm-loading", LoadingIndicator)
        output = self.query_one("#llm-output", Static)
        btn = self.query_one("#btn-llm", Button)
        status = self.query_one("#llm-status", Static)

        btn.disabled = True
        loading.styles.display = "block"
        output.update("")
        status.update("[cyan]Calling LLM…[/cyan]")

        try:
            prompt = format_analytics_prompt(self.store, hours=24)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._llm_client.generate_insight(prompt),  # type: ignore[union-attr]
            )
            output.update(response)
            status.update(f"[green]✓ LLM ready ({self._llm_client.provider.value})[/green]")
        except Exception as exc:
            output.update(f"[red]Error: {exc}[/red]")
            status.update("[red]LLM call failed[/red]")
        finally:
            loading.styles.display = "none"
            btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-llm":
            self.run_worker(self._run_llm_insights(), exclusive=True)


class TextualUI:
    """Textual UI launcher for apimon."""

    def __init__(self, db_path: str = "apimon.db"):
        self.db_path = db_path

    def run(self):
        """Launch the Textual UI."""
        app = DashboardScreen(db_path=self.db_path)
        app.run()


def launch_textual_ui(db_path: str = "apimon.db"):
    """Launch the Textual UI."""
    app = DashboardScreen(db_path=db_path)
    app.run()
