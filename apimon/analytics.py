"""Analytics engine for API monitoring and route improvement suggestions."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.panel import Panel

from apimon.storage import DataStore


@dataclass
class Suggestion:
    """Represents an improvement suggestion."""

    severity: str  # "high", "medium", "low"
    category: str
    message: str
    route: Optional[str] = None
    details: Optional[str] = None


class AnalyticsEngine:
    """Analytics engine for processing API monitoring data."""

    def __init__(self, store: DataStore):
        self.store = store

    def analyze_routes(self) -> list[dict[str, Any]]:
        """Analyze routes and return detailed statistics."""
        stats = self.store.get_route_stats()
        analyzed = []

        for route in stats:
            issues = []

            if route["error_rate"] > 10:
                issues.append({
                    "type": "high_error_rate",
                    "message": f"High error rate: {route['error_rate']:.1f}%",
                    "severity": "high",
                })

            if route["avg_response_time_ms"] > 1000:
                issues.append({
                    "type": "slow_response",
                    "message": f"Slow responses: avg {route['avg_response_time_ms']:.0f}ms",
                    "severity": "medium",
                })

            if route["hit_count"] > 1000 and route["avg_response_time_ms"] > 100:
                issues.append({
                    "type": "frequent_slow_requests",
                    "message": f"High traffic with slow responses ({route['hit_count']} hits)",
                    "severity": "medium",
                })

            analyzed.append({
                **route,
                "issues": issues,
            })

        return analyzed

    def generate_suggestions(self) -> list[Suggestion]:
        """Generate improvement suggestions based on analytics."""
        suggestions = []
        stats = self.store.get_route_stats()
        analytics = self.store.get_analytics_summary()

        # High level analytics suggestions
        if analytics["error_rate"] > 10:
            suggestions.append(Suggestion(
                severity="high",
                category="errors",
                message=f"Overall error rate is {analytics['error_rate']:.1f}%.",
                details="Check server logs and add proper error responses.",
            ))

        if analytics["avg_response_time_ms"] > 500:
            suggestions.append(Suggestion(
                severity="medium",
                category="performance",
                message=f"Average response time is {analytics['avg_response_time_ms']:.0f}ms.",
                details="Look into response caching, database query optimization, or CDN for static assets.",
            ))

        # Route specific suggestions
        slow_routes = [r for r in stats if r["avg_response_time_ms"] > 1000]
        if slow_routes:
            suggestions.append(Suggestion(
                severity="medium",
                category="performance",
                message=f"{len(slow_routes)} routes have slow response times (>1s)",
                details="Consider adding indexing, caching, or async processing for: " +
                        ", ".join(r["route_pattern"] for r in slow_routes[:3]),
            ))

        error_routes = [r for r in stats if r["error_rate"] > 20]
        for route in error_routes:
            suggestions.append(Suggestion(
                severity="high",
                category="errors",
                message=f"Route {route['route_pattern']} has {route['error_rate']:.1f}% error rate",
                details=f"Check endpoint implementation and add proper validation.",
                route=route["route_pattern"],
            ))

        # Pattern: Slow POST/PUT/PATCH could be async
        slow_write_routes = [
            r for r in stats
            if r["method"] in ["POST", "PUT", "PATCH"] and r["avg_response_time_ms"] > 2000
        ]
        for route in slow_write_routes:
            suggestions.append(Suggestion(
                severity="medium",
                category="architecture",
                message=f"Slow write operations on {route['route_pattern']}",
                details="Consider using a background task queue (Celery/RQ) for long-running operations.",
                route=route["route_pattern"],
            ))

        # Pattern: Frequent small GET requests
        chatter_routes = [
            r for r in stats
            if r["method"] == "GET" and r["hit_count"] > 200 and r["avg_response_time_ms"] < 50
        ]
        if chatter_routes:
            suggestions.append(Suggestion(
                severity="low",
                category="efficiency",
                message=f"Potential 'chatty' API pattern detected ({len(chatter_routes)} fast but frequent routes)",
                details="Consider batching requests or using WebSockets for real-time updates.",
            ))

        # Pattern: Caching opportunities
        uncached_get_routes = [
            r for r in stats
            if r["method"] == "GET" and r["hit_count"] > 50 and r["avg_response_time_ms"] > 100
        ]
        if uncached_get_routes:
            suggestions.append(Suggestion(
                severity="low",
                category="caching",
                message=f"{len(uncached_get_routes)} GET routes could benefit from caching",
                details="Consider adding Cache-Control headers or a server-side cache (Redis).",
            ))

        # Pattern: Security
        auth_routes_high_error = [
            r for r in stats
            if ("/auth" in r["route_pattern"].lower() or "/login" in r["route_pattern"].lower())
            and r["error_rate"] > 30
        ]
        if auth_routes_high_error:
            suggestions.append(Suggestion(
                severity="high",
                category="security",
                message="Abnormal error rates on authentication endpoints",
                details="This could indicate brute-force attempts or poor UX leading to failed logins.",
            ))

        return suggestions

    def get_graph_data(self, hours: int = 24) -> dict[str, Any]:
        """Get time-series data for graphing."""
        since = datetime.utcnow() - timedelta(hours=hours)
        requests = self.store.get_recent_requests(limit=10000)

        hourly_data = defaultdict(lambda: {"hits": 0, "errors": 0, "total_time": 0})

        for req in requests:
            ts = datetime.fromisoformat(req["timestamp"])
            if ts >= since:
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                hourly_data[hour_key]["hits"] += 1
                if req.get("is_error"):
                    hourly_data[hour_key]["errors"] += 1
                hourly_data[hour_key]["total_time"] += req.get("response_time_ms", 0)

        result = []
        for hour in sorted(hourly_data.keys()):
            data = hourly_data[hour]
            result.append({
                "hour": hour,
                "hits": data["hits"],
                "errors": data["errors"],
                "avg_response_time": data["total_time"] / data["hits"] if data["hits"] > 0 else 0,
            })

        return {"time_series": result, "hours": hours}

    def render_ascii_graph(
        self,
        data: list[dict[str, Any]],
        value_key: str = "hits",
        max_width: int = 50,
    ) -> str:
        """Render a simple ASCII bar graph."""
        if not data:
            return "No data available."

        max_value = max(d.get(value_key, 0) for d in data) or 1
        lines = []

        for d in data:
            value = d.get(value_key, 0)
            bar_length = int((value / max_value) * max_width)
            bar = "█" * bar_length
            lines.append(f"{d.get('hour', ''):<16} {bar} {value}")

        return "\n".join(lines)

    def print_dashboard(self, console: Optional[Console] = None):
        """Print a rich-formatted dashboard."""
        console = console or Console()
        analytics = self.store.get_analytics_summary()
        stats = self.store.get_route_stats()
        suggestions = self.generate_suggestions()

        console.print(Panel(
            f"[bold]Total Requests:[/bold] {analytics['total_requests']}\n"
            f"[bold]Error Rate:[/bold] {analytics['error_rate']:.1f}%\n"
            f"[bold]Avg Response:[/bold] {analytics['avg_response_time_ms']:.0f}ms\n"
            f"[bold]Unique Routes:[/bold] {analytics['unique_routes']}",
            title="📊 Analytics Overview",
            border_style="blue",
        ))

        if stats:
            table = Table(title="� Routes", show_header=True, header_style="bold magenta")
            table.add_column("Method", style="cyan", width=8)
            table.add_column("Route", style="white")
            table.add_column("Hits", justify="right", style="green")
            table.add_column("Avg ms", justify="right", style="yellow")
            table.add_column("Errors", justify="right", style="red")

            for route in stats[:10]:
                table.add_row(
                    route["method"],
                    route["route_pattern"][:40],
                    str(route["hit_count"]),
                    f"{route['avg_response_time_ms']:.0f}",
                    f"{route['error_count']} ({route['error_rate']:.0f}%)",
                )
            console.print(table)

        if suggestions:
            tree = Tree("💡 Suggestions")
            for s in suggestions[:5]:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "⚪")
                tree.add(f"{severity_emoji} [{s.severity.upper()}] {s.message}")
            console.print(tree)

    def export_json(self, filepath: str):
        """Export all analytics data to JSON."""
        data = {
            "generated_at": datetime.utcnow().isoformat(),
            "analytics_summary": self.store.get_analytics_summary(),
            "route_stats": self.store.get_route_stats(),
            "recent_requests": self.store.get_recent_requests(limit=500),
            "suggestions": [
                {"severity": s.severity, "category": s.category, "message": s.message, "details": s.details}
                for s in self.generate_suggestions()
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


def create_analytics(store: DataStore) -> AnalyticsEngine:
    """Create an analytics engine instance."""
    return AnalyticsEngine(store)
