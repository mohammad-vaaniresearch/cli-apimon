"""HTTP proxy server for API monitoring."""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import aiohttp
from aiohttp import web

from apimon.storage import DataStore


@dataclass
class ProxyConfig:
    """Configuration for the proxy server."""

    target_host: str
    target_port: int
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    db_path: str = "apimon.db"
    record_bodies: bool = True
    excluded_headers: list[str] = field(
        default_factory=lambda: ["authorization", "cookie", "set-cookie"]
    )


class ProxyServer:
    """HTTP proxy server that intercepts and logs API traffic."""

    def __init__(self, config: ProxyConfig):
        self.config = config
        self.app = web.Application()
        self.store = DataStore(config.db_path)
        self.client_session = None
        self._setup_routes()
        self._running = False

    def _setup_routes(self):
        """Set up proxy routes."""
        self.app.router.add_route("*", "/{path:.*}", self._handle_proxy)
        self.app.router.add_get("/_apimon/status", self._handle_status)
        self.app.router.add_get("/_apimon/stats", self._handle_stats)
        self.app.router.add_get("/_apimon/requests", self._handle_requests)
        self.app.router.add_get("/_apimon/request/{id}", self._handle_request_detail)
        self.app.router.add_get("/_apimon/analytics", self._handle_analytics)
        self.app.router.add_get("/_apimon/graph", self._handle_graph)
        self.app.router.add_get("/_apimon/suggestions", self._handle_suggestions)
        self.app.router.add_delete("/_apimon/clear", self._handle_clear)

    def _extract_route_pattern(self, path: str, method: str) -> str:
        """Extract a route pattern from a path."""
        # Replace IDs/UUIDs/Hashes with placeholders
        pattern = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        pattern = re.sub(r"/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=/|$)", "/{uuid}", pattern)
        pattern = re.sub(r"/[a-f0-9]{24,}(?=/|$)", "/{hash}", pattern)
        # Handle common versions
        pattern = re.sub(r"/v\d+", "/v{version}", pattern)
        return pattern

    def _filter_headers(self, headers: dict, is_request: bool = True) -> dict:
        """Filter out sensitive headers."""
        excluded = self.config.excluded_headers
        return {k: v for k, v in headers.items() if k.lower() not in excluded}

    async def _handle_proxy(self, request: web.Request) -> web.Response:
        """Handle proxy requests."""
        start_time = time.time()

        path = request.match_info.get("path", "")
        query_string = str(request.query_string)
        method = request.method

        target_url = f"http://{self.config.target_host}:{self.config.target_port}/{path}"
        if query_string:
            target_url += f"?{query_string}"

        headers = self._filter_headers(dict(request.headers), is_request=True)

        body = None
        if self.config.record_bodies and method in ["POST", "PUT", "PATCH"]:
            body = await request.text()

        try:
            async with self.client_session.request(
                method=method,
                url=target_url,
                headers=headers,
                data=body,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                response_time_ms = (time.time() - start_time) * 1000

                response_headers = self._filter_headers(dict(resp.headers), is_request=False)
                response_body = None
                if self.config.record_bodies:
                    try:
                        response_body = await resp.text()
                    except Exception:
                        response_body = "[binary data]"

                self.store.save_request(
                    method=method,
                    path="/" + path,
                    query_string=query_string,
                    request_headers=headers,
                    request_body=body,
                    response_status=resp.status,
                    response_headers=response_headers,
                    response_body=response_body,
                    response_time_ms=response_time_ms,
                    route_pattern=self._extract_route_pattern("/" + path, method),
                )

                response = web.Response(
                    status=resp.status,
                    headers=response_headers,
                    body=response_body,
                )
                return response

        except aiohttp.ClientError as e:
            response_time_ms = (time.time() - start_time) * 1000
            self.store.save_request(
                method=method,
                path="/" + path,
                query_string=query_string,
                request_headers=headers,
                request_body=body,
                response_status=502,
                response_headers={},
                response_body=f"Proxy Error: {str(e)}",
                response_time_ms=response_time_ms,
                route_pattern=self._extract_route_pattern("/" + path, method),
            )
            return web.Response(status=502, text=f"Proxy Error: {str(e)}")
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            self.store.save_request(
                method=method,
                path="/" + path,
                query_string=query_string,
                request_headers=headers,
                request_body=body,
                response_status=500,
                response_headers={},
                response_body=f"Internal Proxy Error: {str(e)}",
                response_time_ms=response_time_ms,
                route_pattern=self._extract_route_pattern("/" + path, method),
            )
            return web.Response(status=500, text=f"Internal Proxy Error: {str(e)}")

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Return proxy status."""
        return web.json_response({
            "status": "running",
            "target": f"{self.config.target_host}:{self.config.target_port}",
            "listening": f"{self.config.listen_host}:{self.config.listen_port}",
        })

    async def _handle_stats(self, request: web.Request) -> web.Response:
        """Return route statistics."""
        stats = self.store.get_route_stats()
        return web.json_response(stats)

    async def _handle_requests(self, request: web.Request) -> web.Response:
        """Return recent requests."""
        limit = int(request.query.get("limit", 100))
        method = request.query.get("method", None)
        path = request.query.get("path", None)
        requests = self.store.get_recent_requests(limit, method, path)
        return web.json_response(requests)

    async def _handle_request_detail(self, request: web.Request) -> web.Response:
        """Return request detail."""
        request_id = int(request.match_info["id"])
        detail = self.store.get_request_detail(request_id)
        if detail:
            return web.json_response(detail)
        return web.Response(status=404, text="Request not found")

    async def _handle_analytics(self, request: web.Request) -> web.Response:
        """Return analytics summary."""
        hours = int(request.query.get("hours", 24))
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=hours)
        analytics = self.store.get_analytics_summary(since)
        return web.json_response(analytics)

    async def _handle_graph(self, request: web.Request) -> web.Response:
        """Return graph data."""
        hours = int(request.query.get("hours", 24))
        from apimon.analytics import create_analytics
        engine = create_analytics(self.store)
        graph_data = engine.get_graph_data(hours)
        return web.json_response(graph_data)

    async def _handle_suggestions(self, request: web.Request) -> web.Response:
        """Return improvement suggestions."""
        from apimon.analytics import create_analytics
        engine = create_analytics(self.store)
        suggestions = engine.generate_suggestions()
        return web.json_response([
            {
                "severity": s.severity,
                "category": s.category,
                "message": s.message,
                "route": s.route,
                "details": s.details,
            }
            for s in suggestions
        ])

    async def _handle_clear(self, request: web.Request) -> web.Response:
        """Clear all data."""
        self.store.clear_data()
        return web.json_response({"status": "cleared"})

    async def start(self):
        """Start the proxy server."""
        self.client_session = aiohttp.ClientSession()
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(
            runner,
            self.config.listen_host,
            self.config.listen_port,
        )
        await site.start()
        self._running = True
        print(f"🚀 apimon proxy running on http://{self.config.listen_host}:{self.config.listen_port}")
        print(f"   → forwarding to http://{self.config.target_host}:{self.config.target_port}")
        print(f"   → use --target to configure the backend API server")

    async def run_forever(self):
        """Run the proxy server forever."""
        await self.start()
        await asyncio.Event().wait()

    def run(self):
        """Run the proxy server synchronously."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_app():
            self.client_session = aiohttp.ClientSession()
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(
                runner,
                self.config.listen_host,
                self.config.listen_port,
            )
            await site.start()
            print(f"🚀 apimon proxy running on http://{self.config.listen_host}:{self.config.listen_port}")
            print(f"   → forwarding to http://{self.config.target_host}:{self.config.target_port}")
            print(f"   → use --target to configure the backend API server")
            
            # Run forever
            await asyncio.Event().wait()
        
        try:
            loop.run_until_complete(run_app())
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(self.client_session.close())
            loop.close()
            self.store.close()


def create_proxy_server(
    target_host: str,
    target_port: int,
    listen_port: int = 8080,
    db_path: str = "apimon.db",
) -> ProxyServer:
    """Create a proxy server instance."""
    config = ProxyConfig(
        target_host=target_host,
        target_port=target_port,
        listen_port=listen_port,
        db_path=db_path,
    )
    return ProxyServer(config)
