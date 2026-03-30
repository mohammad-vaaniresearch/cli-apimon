"""Main CLI entry point for apimon."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from apimon import __version__
from apimon.proxy import create_proxy_server, ProxyServer
from apimon.storage import DataStore
from apimon.analytics import AnalyticsEngine, create_analytics
from apimon.ui.textual_ui import launch_textual_ui


console = Console()


def check_node_available() -> bool:
    """Check if Node.js is available for the Ink UI."""
    try:
        import subprocess
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@click.group()
@click.version_option(version=__version__)
@click.option("--db-path", default="apimon.db", help="Path to SQLite database")
@click.pass_context
def cli(ctx, db_path):
    """apimon - API monitoring and analytics CLI tool."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["store"] = DataStore(db_path)


@cli.command()
@click.option("--target-host", default="localhost", help="Target API server host")
@click.option("--target-port", default=3000, help="Target API server port")
@click.option("--port", "-p", default=8080, help="Proxy listen port")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def proxy(ctx, target_host, target_port, port, db_path):
    """Start the API proxy server for monitoring."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")

    console.print(f"[cyan]Starting apimon proxy...[/cyan]")
    console.print(f"  Target: http://{target_host}:{target_port}")
    console.print(f"  Listen: http://127.0.0.1:{port}")
    console.print(f"  Database: {path}")
    console.print("")

    server = create_proxy_server(
        target_host=target_host,
        target_port=target_port,
        listen_port=port,
        db_path=path,
    )

    try:
        server.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        server.store.close()


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.option("--port", "-p", default=8080, help="Proxy port")
@click.pass_context
def ui(ctx, db_path, port):
    """Launch the interactive dashboard UI."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")

    if check_node_available():
        console.print("[green]Node.js detected, launching Ink UI...[/green]")
        try:
            import subprocess
            frontend_path = Path(__file__).parent.parent.parent / "frontend"
            if frontend_path.exists():
                result = subprocess.run(
                    ["npm", "start", "--", "--db-path", path, "--port", str(port)],
                    cwd=str(frontend_path),
                    env={**os.environ, "APIMON_DB_PATH": path, "APIMON_PORT": str(port)},
                )
                if result.returncode != 0:
                    console.print("[yellow]Ink UI failed, falling back to Textual...[/yellow]")
                    launch_textual_ui(path)
            else:
                launch_textual_ui(path)
        except Exception as e:
            console.print(f"[yellow]Ink UI error: {e}, falling back to Textual...[/yellow]")
            launch_textual_ui(path)
    else:
        console.print("[yellow]Node.js not available, using Textual UI...[/yellow]")
        launch_textual_ui(path)


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def dashboard(ctx, db_path):
    """Show analytics dashboard in terminal."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    analytics.print_dashboard()
    store.close()


@cli.command()
@click.option("--hours", default=24, help="Time range in hours")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def stats(ctx, hours, db_path):
    """Show route statistics."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    stats_data = store.get_route_stats()
    if not stats_data:
        console.print("[yellow]No data available yet. Start the proxy and make some requests.[/yellow]")
        store.close()
        return

    from rich.table import Table
    table = Table(title=f"Route Statistics (last {hours}h)", show_header=True)
    table.add_column("Method", style="cyan", width=8)
    table.add_column("Route", style="white")
    table.add_column("Hits", justify="right", style="green")
    table.add_column("Avg ms", justify="right", style="yellow")
    table.add_column("Min ms", justify="right")
    table.add_column("Max ms", justify="right")
    table.add_column("Errors", justify="right", style="red")

    for route in stats_data:
        table.add_row(
            route["method"],
            route["route_pattern"][:45],
            str(route["hit_count"]),
            f"{route['avg_response_time_ms']:.1f}",
            f"{route['min_response_time_ms']:.1f}" if route["min_response_time_ms"] else "-",
            f"{route['max_response_time_ms']:.1f}" if route["max_response_time_ms"] else "-",
            f"{route['error_count']} ({route['error_rate']:.1f}%)",
        )

    console.print(table)
    store.close()


@cli.command()
@click.option("--limit", default=50, help="Number of requests to show")
@click.option("--method", default=None, help="Filter by HTTP method")
@click.option("--path", default=None, help="Filter by path pattern")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def requests(ctx, limit, method, path, db_path):
    """Show recent API requests."""
    path_db = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path_db)

    requests_data = store.get_recent_requests(limit, method, path)
    if not requests_data:
        console.print("[yellow]No requests recorded yet.[/yellow]")
        store.close()
        return

    from rich.table import Table
    table = Table(title="Recent Requests", show_header=True)
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Method", style="cyan", width=8)
    table.add_column("Path", style="white")
    table.add_column("Status", justify="right")
    table.add_column("Time", justify="right", style="yellow")
    table.add_column("Timestamp", style="dim")

    for req in requests_data:
        status_style = "red" if req["response_status"] >= 400 else "green"
        table.add_row(
            str(req["id"]),
            req["method"],
            req["path"][:40],
            f"[{status_style}]{req['response_status']}[/{status_style}]",
            f"{req['response_time_ms']:.1f}ms",
            req["timestamp"][:19],
        )

    console.print(table)
    store.close()


@cli.command()
@click.argument("request_id", type=int)
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def request(ctx, request_id, db_path):
    """Show detailed view of a specific request."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)

    detail = store.get_request_detail(request_id)
    if not detail:
        console.print(f"[red]Request #{request_id} not found[/red]")
        store.close()
        return

    console.print(f"[bold]Request #{detail['id']}[/bold]")
    console.print(f"[cyan]Method:[/cyan] {detail['method']}")
    console.print(f"[cyan]Path:[/cyan] {detail['path']}")
    console.print(f"[cyan]Status:[/cyan] {detail['response_status']}")
    console.print(f"[cyan]Response Time:[/cyan] {detail['response_time_ms']:.1f}ms")
    console.print(f"[cyan]Timestamp:[/cyan] {detail['timestamp']}")
    console.print("")

    console.print("[bold]Request Headers:[/bold]")
    for k, v in detail.get("request_headers", {}).items():
        console.print(f"  {k}: {v}")

    if detail.get("request_body"):
        console.print("")
        console.print("[bold]Request Body:[/bold]")
        console.print(detail["request_body"][:500])

    console.print("")
    console.print("[bold]Response Headers:[/bold]")
    for k, v in detail.get("response_headers", {}).items():
        console.print(f"  {k}: {v}")

    if detail.get("response_body"):
        console.print("")
        console.print("[bold]Response Body:[/bold]")
        console.print(detail["response_body"][:500])

    store.close()


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def suggestions(ctx, db_path):
    """Show improvement suggestions based on analytics."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    suggestions_data = analytics.generate_suggestions()
    if not suggestions_data:
        console.print("[green]No issues detected! Your API looks healthy.[/green]")
        store.close()
        return

    from rich.tree import Tree
    tree = Tree("💡 Improvement Suggestions")

    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_suggestions = sorted(
        suggestions_data,
        key=lambda s: severity_order.get(s.severity, 3)
    )

    for s in sorted_suggestions:
        emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "⚪")
        label = f"{emoji} [{s.severity.upper()}] {s.message}"
        if s.route:
            label += f" ({s.route})"
        branch = tree.add(label)
        if s.details:
            branch.add(s.details)

    console.print(tree)
    store.close()


@cli.command()
@click.option("--hours", default=24, help="Time range in hours")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def graph(ctx, hours, db_path):
    """Show ASCII graph of request activity."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    graph_data = analytics.get_graph_data(hours)
    time_series = graph_data.get("time_series", [])

    if not time_series:
        console.print("[yellow]No data available for graphing.[/yellow]")
        store.close()
        return

    console.print(f"[bold]Request Activity (last {hours}h)[/bold]")
    console.print("")
    console.print("[bold]Hits:[/bold]")
    console.print(analytics.render_ascii_graph(time_series, "hits"))
    console.print("")
    console.print("[bold]Errors:[/bold]")
    console.print(analytics.render_ascii_graph(time_series, "errors"))
    console.print("")
    console.print("[bold]Avg Response Time (ms):[/bold]")
    console.print(analytics.render_ascii_graph(time_series, "avg_response_time"))

    store.close()


@cli.command()
@click.argument("filepath", type=click.Path())
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def export(ctx, filepath, db_path):
    """Export analytics data to JSON file."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    analytics.export_json(filepath)
    console.print(f"[green]✅ Exported analytics to {filepath}[/green]")

    store.close()


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def clear(ctx, db_path):
    """Clear all stored data."""
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)

    store.clear_data()
    console.print("[green]✅ All data cleared[/green]")

    store.close()


@cli.command()
@click.pass_context
def version(ctx):
    """Show apimon version."""
    console.print(f"apimon version {__version__}")


if __name__ == "__main__":
    cli()
