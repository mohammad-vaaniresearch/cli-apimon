"""Main CLI entry point for apimon."""

import asyncio
import json
import os
import sys
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from apimon import __version__
from apimon.proxy import create_proxy_server
from apimon.storage import DataStore
from apimon.analytics import AnalyticsEngine, create_analytics
from apimon.ui.textual_ui import launch_textual_ui
from apimon.llm import (
    LLMProvider,
    create_llm_client,
    try_create_llm_client,
    LLMInsightGenerator,
    format_analytics_prompt,
    get_provider_choices,
)


console = Console()


def _emit(data: object, as_json: bool) -> None:
    """Print data as JSON (for --json / --ai) or do nothing (caller handles human output)."""
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))


@click.group()
@click.version_option(version=__version__)
@click.option("--db-path", default="apimon.db", help="Path to SQLite database")
@click.pass_context
def cli(ctx, db_path):
    """apimon - API monitoring and analytics CLI tool.

    \b
    Examples:
      apimon proxy --target-port 3000          # start capturing traffic
      apimon ui                                # interactive TUI dashboard
      apimon ui --ai                           # machine-readable snapshot (no TUI)
      apimon stats --json                      # route stats as JSON
      apimon requests --json --limit 20        # recent requests as JSON
      apimon suggestions --json                # rule-based suggestions as JSON
      apimon insights --provider openai        # LLM-powered analysis
    """
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
    """Start the API proxy server for monitoring.

    \b
    Examples:
      apimon proxy                              # proxy localhost:3000 -> :8080
      apimon proxy --target-port 4000           # different target port
      apimon proxy --port 9090 --target-port 3000
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")

    console.print("[cyan]Starting apimon proxy...[/cyan]")
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
@click.option(
    "--ai",
    is_flag=True,
    default=False,
    help="Non-interactive mode: print full snapshot as JSON and exit (no TUI). "
         "Optionally calls the LLM when --provider + key are available.",
)
@click.option(
    "--provider",
    type=click.Choice(get_provider_choices()),
    default=None,
    help="LLM provider for --ai mode (reads key from env if not given with --api-key).",
)
@click.option("--api-key", default=None, help="LLM API key for --ai mode.")
@click.option("--hours", default=24, help="Time range in hours for --ai mode analysis.")
@click.pass_context
def ui(ctx, db_path, port, ai, provider, api_key, hours):
    """Launch the interactive dashboard UI, or dump a full JSON snapshot.

    \b
    Examples:
      apimon ui                                # interactive Textual dashboard
      apimon ui --ai                           # JSON snapshot, no TUI
      apimon ui --ai --provider openai         # JSON snapshot + LLM insights (key from OPENAI_API_KEY)
      apimon ui --ai --provider openai --api-key sk-...
      apimon ui --ai | jq .analytics_summary
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")

    if not ai:
        console.print("[cyan]Launching Textual UI...[/cyan]")
        launch_textual_ui(path)
        return

    # ── AI / non-interactive mode ────────────────────────────────────────────
    store = DataStore(path)
    analytics_engine = create_analytics(store)

    analytics_summary = store.get_analytics_summary()
    route_stats = store.get_route_stats()
    status_distribution = store.get_status_code_distribution(hours=hours)
    method_distribution = store.get_method_distribution(hours=hours)
    error_summary = store.get_error_summary(hours=hours)
    slowest_routes = store.get_slowest_routes(hours=hours, limit=10)
    hourly_summary = store.get_hourly_summary(hours=hours)
    top_routes = store.get_top_routes_by_traffic(hours=hours, limit=10)
    error_messages = store.get_unique_error_messages(hours=hours, limit=15)
    cache_candidates = store.get_cache_candidates(hours=hours)
    percentiles = store.get_response_time_percentiles(hours=hours)
    route_percentiles = store.get_route_percentiles(hours=hours, limit=10)
    error_trend = store.get_error_rate_by_hour(hours=hours)

    suggestions_raw = analytics_engine.generate_suggestions()
    suggestions = [
        {
            "severity": s.severity,
            "category": s.category,
            "message": s.message,
            "route": s.route,
            "details": s.details,
        }
        for s in suggestions_raw
    ]

    llm_prompt = format_analytics_prompt(store, hours=hours)

    llm_insights: Optional[str] = None
    llm_error: Optional[str] = None
    llm_provider_used: Optional[str] = None

    if provider:
        try:
            provider_enum = LLMProvider(provider)
            client = try_create_llm_client(provider_enum, api_key)
            if client is None:
                llm_error = (
                    f"Could not initialise {provider} client. "
                    "Check that the API key is set (env or --api-key)."
                )
            else:
                llm_provider_used = client.provider.value
                generator = LLMInsightGenerator(store, client)
                llm_insights = generator.generate_insights(hours=hours)
        except Exception as exc:
            llm_error = str(exc)

    output = {
        "apimon_version": __version__,
        "db_path": path,
        "hours_analyzed": hours,
        "analytics_summary": analytics_summary,
        "response_time_percentiles": percentiles,
        "route_stats": route_stats,
        "top_routes_by_traffic": top_routes,
        "route_percentiles": route_percentiles,
        "status_code_distribution": status_distribution,
        "method_distribution": method_distribution,
        "error_summary": error_summary,
        "unique_error_messages": error_messages,
        "slowest_routes": slowest_routes,
        "cache_candidates": cache_candidates,
        "hourly_summary": hourly_summary,
        "error_rate_trend": error_trend,
        "suggestions": suggestions,
        "llm_prompt": llm_prompt,
        "llm_provider": llm_provider_used,
        "llm_insights": llm_insights,
        "llm_error": llm_error,
    }

    click.echo(json.dumps(output, indent=2, default=str))
    store.close()


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.pass_context
def dashboard(ctx, db_path):
    """Show analytics dashboard in terminal.

    \b
    Examples:
      apimon dashboard
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    analytics.print_dashboard()
    store.close()


@cli.command()
@click.option("--hours", default=24, help="Time range in hours")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def stats(ctx, hours, db_path, as_json):
    """Show route statistics.

    \b
    Examples:
      apimon stats
      apimon stats --hours 1
      apimon stats --json
      apimon stats --json | jq '.[] | select(.error_rate > 5)'
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)

    stats_data = store.get_route_stats()
    if not stats_data:
        if as_json:
            click.echo(json.dumps([]))
        else:
            console.print("[yellow]No data available yet. Start the proxy and make some requests.[/yellow]")
        store.close()
        return

    if as_json:
        click.echo(json.dumps(stats_data, indent=2, default=str))
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
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def requests(ctx, limit, method, path, db_path, as_json):
    """Show recent API requests.

    \b
    Examples:
      apimon requests
      apimon requests --limit 100 --method GET
      apimon requests --json
      apimon requests --json --method POST | jq '.[] | select(.response_status >= 400)'
    """
    path_db = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path_db)

    requests_data = store.get_recent_requests(limit, method, path)
    if not requests_data:
        if as_json:
            click.echo(json.dumps([]))
        else:
            console.print("[yellow]No requests recorded yet.[/yellow]")
        store.close()
        return

    if as_json:
        click.echo(json.dumps(requests_data, indent=2, default=str))
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
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def request(ctx, request_id, db_path, as_json):
    """Show detailed view of a specific request.

    \b
    Examples:
      apimon request 42
      apimon request 42 --json
      apimon request 42 --json | jq .response_body
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)

    detail = store.get_request_detail(request_id)
    if not detail:
        if as_json:
            click.echo(json.dumps({"error": f"Request #{request_id} not found"}))
        else:
            console.print(f"[red]Request #{request_id} not found[/red]")
        store.close()
        return

    if as_json:
        click.echo(json.dumps(detail, indent=2, default=str))
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
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def suggestions(ctx, db_path, as_json):
    """Show improvement suggestions based on analytics.

    \b
    Examples:
      apimon suggestions
      apimon suggestions --json
      apimon suggestions --json | jq '.[] | select(.severity == "high")'
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    suggestions_data = analytics.generate_suggestions()

    if as_json:
        click.echo(json.dumps(
            [
                {
                    "severity": s.severity,
                    "category": s.category,
                    "message": s.message,
                    "route": s.route,
                    "details": s.details,
                }
                for s in suggestions_data
            ],
            indent=2,
        ))
        store.close()
        return

    if not suggestions_data:
        console.print("[green]No issues detected! Your API looks healthy.[/green]")
        store.close()
        return

    from rich.tree import Tree
    tree = Tree("💡 Improvement Suggestions")

    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_suggestions = sorted(
        suggestions_data,
        key=lambda s: severity_order.get(s.severity, 3),
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
@click.option(
    "--provider", "-p",
    type=click.Choice(get_provider_choices()),
    default="openai",
    help="LLM provider to use",
)
@click.option("--api-key", default=None, help="API key (or set env var)")
@click.option("--model", default=None, help="Model override (uses provider default if omitted)")
@click.option("--hours", default=24, help="Time range in hours to analyze")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def insights(ctx, provider, api_key, model, hours, db_path, as_json):
    """Generate AI-powered insights from analytics using an LLM.

    \b
    Examples:
      apimon insights                          # OpenAI, key from OPENAI_API_KEY
      apimon insights --provider gemini        # Gemini, key from GEMINI_API_KEY
      apimon insights --provider anthropic --api-key sk-ant-...
      apimon insights --json                   # machine-readable output
      apimon insights --json | jq .insights
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)

    summary = store.get_analytics_summary()
    if summary["total_requests"] == 0:
        if as_json:
            click.echo(json.dumps({"error": "No data available. Run the proxy first."}))
        else:
            console.print("[yellow]No data available. Start the proxy and make some requests first.[/yellow]")
        store.close()
        return

    try:
        provider_enum = LLMProvider(provider)
        client = create_llm_client(provider_enum, api_key)
    except ValueError as e:
        if as_json:
            click.echo(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]{e}[/red]")
        store.close()
        return

    generator = LLMInsightGenerator(store, client)
    insights_text = generator.generate_insights(hours=hours, model=model)

    if as_json:
        click.echo(json.dumps({"provider": provider, "model": model, "insights": insights_text}, indent=2))
    else:
        generator.print_insights(insights_text)

    store.close()


@cli.command()
@click.option("--hours", default=24, help="Time range in hours")
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def graph(ctx, hours, db_path, as_json):
    """Show ASCII graph of request activity.

    \b
    Examples:
      apimon graph
      apimon graph --hours 1
      apimon graph --json
      apimon graph --json | jq .time_series
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    graph_data = analytics.get_graph_data(hours)
    time_series = graph_data.get("time_series", [])

    if not time_series:
        if as_json:
            click.echo(json.dumps({"time_series": []}))
        else:
            console.print("[yellow]No data available for graphing.[/yellow]")
        store.close()
        return

    if as_json:
        click.echo(json.dumps(graph_data, indent=2, default=str))
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
    """Export analytics data to a JSON file.

    \b
    Examples:
      apimon export report.json
      apimon export /tmp/apimon-$(date +%s).json
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")
    store = DataStore(path)
    analytics = create_analytics(store)

    analytics.export_json(filepath)
    console.print(f"[green]✅ Exported analytics to {filepath}[/green]")

    store.close()


@cli.command()
@click.option("--db-path", default=None, help="Database path (overrides global)")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_context
def clear(ctx, db_path, yes):
    """Clear all stored data.

    \b
    Examples:
      apimon clear          # prompts for confirmation
      apimon clear --yes    # non-interactive, safe for scripts/agents
    """
    path = db_path or ctx.obj.get("db_path", "apimon.db")

    if not yes:
        click.confirm("Delete all captured data?", abort=True)

    store = DataStore(path)
    store.clear_data()
    console.print("[green]✅ All data cleared[/green]")
    store.close()


@cli.command()
@click.pass_context
def version(ctx):
    """Show apimon version.

    \b
    Examples:
      apimon version
    """
    console.print(f"apimon version {__version__}")


if __name__ == "__main__":
    cli()
