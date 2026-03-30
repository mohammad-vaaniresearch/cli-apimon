"""Textual-based CLI UI for apimon (fallback when Node.js is unavailable)."""

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    TabbedContent,
    Tabs,
    Tab,
    Log,
    Button,
    Input,
    Label,
)
from textual.events import Key
from textual.reactive import reactive

from apimon.storage import DataStore
from apimon.analytics import AnalyticsEngine


class DashboardScreen(App):
    """Main dashboard screen for apimon Textual UI."""

    CSS = """
    Screen {
        background: $surface;
    }
    .stats-panel {
        height: 3;
        background: $panel;
        dock: top;
    }
    .stats-label {
        text-style: bold;
        color: $accent;
    }
    #stats-table {
        height: 10;
    }
    .route-table {
        height: 1fr;
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
        from textual.widgets import TabPane
        with TabbedContent(initial="routes"):
            with TabPane("Routes", id="routes"):
                yield DataTable(id="routes-table")
            with TabPane("Requests", id="requests"):
                yield DataTable(id="requests-table")
            with TabPane("Analytics", id="analytics"):
                yield Static("", id="analytics-content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "apimon - API Monitor"
        self.sub_title = "Textual UI"
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
        analytics = self.store.get_analytics_summary()
        suggestions = self.analytics.generate_suggestions()

        graph_data = self.analytics.get_graph_data(hours=1)
        graph = self.analytics.render_ascii_graph(graph_data.get("time_series", [])[:10])

        text = f"""
[bold]Analytics Summary[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Requests:  {analytics['total_requests']}
Error Rate:      {analytics['error_rate']:.1f}%
Avg Response:    {analytics['avg_response_time_ms']:.0f}ms
Unique Routes:   {analytics['unique_routes']}

[bold]Time Series (last hour)[/bold]
{graph}

[bold]Suggestions[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for s in suggestions[:5]:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "⚪")
            text += f"\n{emoji} [{s.severity.upper()}] {s.message}"

        content.update(text)


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
