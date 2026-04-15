"""Data storage layer using SQLAlchemy with SQLite."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    Index,
    JSON,
    case,
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

Base = declarative_base()


class RequestRecord(Base):
    """Store individual API request/response data."""

    __tablename__ = "requests"

    id = Column(Integer, primary_key=True)
    method = Column(String(10), nullable=False)
    path = Column(String(2048), nullable=False)
    query_string = Column(Text, default="")
    request_headers = Column(JSON, default=dict)
    request_body = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=False)
    response_headers = Column(JSON, default=dict)
    response_body = Column(Text, nullable=True)
    response_time_ms = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_error = Column(Boolean, default=False)
    route_pattern = Column(String(512), nullable=True)

    __table_args__ = (
        Index("idx_timestamp", "timestamp"),
        Index("idx_path", "path"),
        Index("idx_method", "method"),
        Index("idx_route_pattern", "route_pattern"),
    )


class RouteStats(Base):
    """Aggregated route statistics."""

    __tablename__ = "route_stats"

    id = Column(Integer, primary_key=True)
    route_pattern = Column(String(512), nullable=False, unique=True)
    method = Column(String(10), nullable=False)
    hit_count = Column(Integer, default=0)
    total_response_time_ms = Column(Float, default=0)
    min_response_time_ms = Column(Float, nullable=True)
    max_response_time_ms = Column(Float, nullable=True)
    error_count = Column(Integer, default=0)
    last_request_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_route_method", "route_pattern", "method"),
    )


class DataStore:
    """SQLite-backed data store for API monitoring."""

    def __init__(self, db_path: str = "apimon.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_request(
        self,
        method: str,
        path: str,
        query_string: str,
        request_headers: dict,
        request_body: Optional[str],
        response_status: int,
        response_headers: dict,
        response_body: Optional[str],
        response_time_ms: float,
        route_pattern: Optional[str] = None,
    ) -> int:
        """Save a request/response record and update route stats."""
        with self.Session() as session:
            record = RequestRecord(
                method=method,
                path=path,
                query_string=query_string,
                request_headers=request_headers,
                request_body=request_body[:10000] if request_body else None,
                response_status=response_status,
                response_headers=response_headers,
                response_body=response_body[:10000] if response_body else None,
                response_time_ms=response_time_ms,
                is_error=response_status >= 400,
                route_pattern=route_pattern,
            )
            session.add(record)
            session.flush()

            self._update_route_stats(
                session,
                route_pattern or path,
                method,
                response_time_ms,
                response_status >= 400,
            )

            session.commit()
            return record.id

    def _update_route_stats(
        self,
        session: Session,
        route_pattern: str,
        method: str,
        response_time_ms: float,
        is_error: bool,
    ):
        """Update or insert route statistics."""
        stmt = sqlite_insert(RouteStats).values(
            route_pattern=route_pattern,
            method=method,
            hit_count=1,
            total_response_time_ms=response_time_ms,
            min_response_time_ms=response_time_ms,
            max_response_time_ms=response_time_ms,
            error_count=1 if is_error else 0,
            last_request_at=datetime.utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["route_pattern"],
            set_={
                "hit_count": RouteStats.hit_count + 1,
                "total_response_time_ms": RouteStats.total_response_time_ms
                + response_time_ms,
                "min_response_time_ms": case(
                    (RouteStats.min_response_time_ms < response_time_ms, RouteStats.min_response_time_ms),
                    else_=response_time_ms
                ),
                "max_response_time_ms": case(
                    (RouteStats.max_response_time_ms > response_time_ms, RouteStats.max_response_time_ms),
                    else_=response_time_ms
                ),
                "error_count": RouteStats.error_count + (1 if is_error else 0),
                "last_request_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )
        session.execute(stmt)

    def get_route_stats(self) -> list[dict[str, Any]]:
        """Get all route statistics."""
        with self.Session() as session:
            routes = session.query(RouteStats).order_by(RouteStats.hit_count.desc()).all()
            return [
                {
                    "route_pattern": r.route_pattern,
                    "method": r.method,
                    "hit_count": r.hit_count,
                    "avg_response_time_ms": (
                        r.total_response_time_ms / r.hit_count
                        if r.hit_count > 0
                        else 0
                    ),
                    "min_response_time_ms": r.min_response_time_ms,
                    "max_response_time_ms": r.max_response_time_ms,
                    "error_count": r.error_count,
                    "error_rate": (r.error_count / r.hit_count * 100) if r.hit_count > 0 else 0,
                    "last_request_at": r.last_request_at.isoformat() if r.last_request_at else None,
                }
                for r in routes
            ]

    def get_recent_requests(
        self,
        limit: int = 100,
        method: Optional[str] = None,
        path_pattern: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get recent request records."""
        with self.Session() as session:
            query = session.query(RequestRecord).order_by(
                RequestRecord.timestamp.desc()
            )
            if method:
                query = query.filter(RequestRecord.method == method.upper())
            if path_pattern:
                query = query.filter(RequestRecord.path.like(f"%{path_pattern}%"))
            records = query.limit(limit).all()
            return [
                {
                    "id": r.id,
                    "method": r.method,
                    "path": r.path,
                    "query_string": r.query_string,
                    "response_status": r.response_status,
                    "response_time_ms": r.response_time_ms,
                    "timestamp": r.timestamp.isoformat(),
                    "is_error": r.is_error,
                    "route_pattern": r.route_pattern,
                }
                for r in records
            ]

    def get_request_detail(self, request_id: int) -> Optional[dict[str, Any]]:
        """Get full details of a specific request."""
        with self.Session() as session:
            record = session.query(RequestRecord).filter(
                RequestRecord.id == request_id
            ).first()
            if record:
                return {
                    "id": record.id,
                    "method": record.method,
                    "path": record.path,
                    "query_string": record.query_string,
                    "request_headers": record.request_headers,
                    "request_body": record.request_body,
                    "response_status": record.response_status,
                    "response_headers": record.response_headers,
                    "response_body": record.response_body,
                    "response_time_ms": record.response_time_ms,
                    "timestamp": record.timestamp.isoformat(),
                    "is_error": record.is_error,
                    "route_pattern": record.route_pattern,
                }
            return None

    def get_analytics_summary(
        self,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get overall analytics summary."""
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        with self.Session() as session:
            total_requests = (
                session.query(RequestRecord)
                .filter(RequestRecord.timestamp >= since)
                .count()
            )
            error_requests = (
                session.query(RequestRecord)
                .filter(RequestRecord.timestamp >= since)
                .filter(RequestRecord.is_error == True)
                .count()
            )
            unique_routes = (
                session.query(RequestRecord.route_pattern)
                .filter(RequestRecord.timestamp >= since)
                .distinct()
                .count()
            )

            avg_response_time = session.query(
                RequestRecord.response_time_ms
            ).filter(RequestRecord.timestamp >= since).all()
            if avg_response_time:
                avg_ms = sum(r[0] for r in avg_response_time) / len(avg_response_time)
            else:
                avg_ms = 0

            return {
                "total_requests": total_requests,
                "error_requests": error_requests,
                "error_rate": (error_requests / total_requests * 100) if total_requests > 0 else 0,
                "unique_routes": unique_routes,
                "avg_response_time_ms": avg_ms,
                "since": since.isoformat(),
            }

    def get_status_code_distribution(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get distribution of HTTP status codes."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.response_status,
                    func.count(RequestRecord.id).label("count"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(RequestRecord.response_status)
                .order_by(func.count(RequestRecord.id).desc())
                .all()
            )
            return [{"status_code": r[0], "count": r[1]} for r in results]

    def get_method_distribution(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get distribution of HTTP methods."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.method,
                    func.count(RequestRecord.id).label("count"),
                    func.avg(RequestRecord.response_time_ms).label("avg_ms"),
                    func.sum(case((RequestRecord.is_error == True, 1), else_=0)).label("errors"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(RequestRecord.method)
                .order_by(func.count(RequestRecord.id).desc())
                .all()
            )
            return [
                {
                    "method": r[0],
                    "count": r[1],
                    "avg_response_time_ms": round(r[2], 2) if r[2] else 0,
                    "error_count": r[3],
                }
                for r in results
            ]

    def get_error_summary(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get summary of errors grouped by route and status code."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    RequestRecord.response_status,
                    func.count(RequestRecord.id).label("count"),
                )
                .filter(RequestRecord.timestamp >= since)
                .filter(RequestRecord.is_error == True)
                .group_by(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    RequestRecord.response_status,
                )
                .order_by(func.count(RequestRecord.id).desc())
                .limit(20)
                .all()
            )
            return [
                {
                    "route": r[0],
                    "method": r[1],
                    "status_code": r[2],
                    "count": r[3],
                }
                for r in results
            ]

    def get_slowest_routes(self, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
        """Get slowest routes by average response time."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    func.count(RequestRecord.id).label("count"),
                    func.avg(RequestRecord.response_time_ms).label("avg_ms"),
                    func.min(RequestRecord.response_time_ms).label("min_ms"),
                    func.max(RequestRecord.response_time_ms).label("max_ms"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(RequestRecord.route_pattern, RequestRecord.method)
                .having(func.count(RequestRecord.id) >= 5)
                .order_by(func.avg(RequestRecord.response_time_ms).desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "route": r[0],
                    "method": r[1],
                    "count": r[2],
                    "avg_response_time_ms": round(r[3], 2) if r[3] else 0,
                    "min_response_time_ms": round(r[4], 2) if r[4] else 0,
                    "max_response_time_ms": round(r[5], 2) if r[5] else 0,
                }
                for r in results
            ]

    def get_hourly_summary(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get hourly aggregated summary."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp).label("hour"),
                    func.count(RequestRecord.id).label("requests"),
                    func.sum(case((RequestRecord.is_error == True, 1), else_=0)).label("errors"),
                    func.avg(RequestRecord.response_time_ms).label("avg_ms"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp))
                .order_by(func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp))
                .all()
            )
            return [
                {
                    "hour": r[0],
                    "requests": r[1],
                    "errors": r[2],
                    "avg_response_time_ms": round(r[3], 2) if r[3] else 0,
                }
                for r in results
            ]

    def get_unique_error_messages(self, hours: int = 24, limit: int = 20) -> list[dict[str, Any]]:
        """Get unique error response bodies grouped by route and status."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    RequestRecord.response_status,
                    RequestRecord.response_body,
                    func.count(RequestRecord.id).label("count"),
                )
                .filter(RequestRecord.timestamp >= since)
                .filter(RequestRecord.is_error == True)
                .filter(RequestRecord.response_body.isnot(None))
                .filter(RequestRecord.response_body != "")
                .group_by(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    RequestRecord.response_status,
                    RequestRecord.response_body,
                )
                .order_by(func.count(RequestRecord.id).desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "route": r[0],
                    "method": r[1],
                    "status_code": r[2],
                    "error_body": (r[3][:500] if r[3] else None),
                    "count": r[4],
                }
                for r in results
            ]

    def get_cache_candidates(self, hours: int = 24, min_hits: int = 10) -> list[dict[str, Any]]:
        """Get GET routes that are good candidates for caching (high hits, low errors, consistent responses)."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.route_pattern,
                    func.count(RequestRecord.id).label("hits"),
                    func.avg(RequestRecord.response_time_ms).label("avg_ms"),
                    func.sum(case((RequestRecord.is_error == True, 1), else_=0)).label("errors"),
                    func.count(func.distinct(RequestRecord.response_status)).label("unique_statuses"),
                )
                .filter(RequestRecord.timestamp >= since)
                .filter(RequestRecord.method == "GET")
                .group_by(RequestRecord.route_pattern)
                .having(func.count(RequestRecord.id) >= min_hits)
                .order_by(func.count(RequestRecord.id).desc())
                .all()
            )
            candidates = []
            for r in results:
                hits = r[1]
                errors = r[3] or 0
                error_rate = (errors / hits * 100) if hits > 0 else 0
                if error_rate < 10:
                    candidates.append({
                        "route": r[0],
                        "hits": hits,
                        "avg_response_time_ms": round(r[2], 2) if r[2] else 0,
                        "error_rate": round(error_rate, 2),
                        "cache_benefit_score": round(hits * (r[2] or 0) / 1000, 2),
                    })
            return sorted(candidates, key=lambda x: x["cache_benefit_score"], reverse=True)[:10]

    def get_response_time_percentiles(self, hours: int = 24) -> dict[str, Any]:
        """Get response time percentiles (p50, p90, p95, p99)."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            results = (
                session.query(RequestRecord.response_time_ms)
                .filter(RequestRecord.timestamp >= since)
                .order_by(RequestRecord.response_time_ms)
                .all()
            )
            if not results:
                return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "sample_size": 0}

            times = [r[0] for r in results]
            n = len(times)

            def percentile(p: int) -> float:
                idx = int(n * p / 100)
                return round(times[min(idx, n - 1)], 2)

            return {
                "p50": percentile(50),
                "p90": percentile(90),
                "p95": percentile(95),
                "p99": percentile(99),
                "sample_size": n,
            }

    def get_route_percentiles(self, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
        """Get response time percentiles per route."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            routes = (
                session.query(RequestRecord.route_pattern, RequestRecord.method)
                .filter(RequestRecord.timestamp >= since)
                .group_by(RequestRecord.route_pattern, RequestRecord.method)
                .having(func.count(RequestRecord.id) >= 20)
                .order_by(func.count(RequestRecord.id).desc())
                .limit(limit)
                .all()
            )

            results = []
            for route, method in routes:
                times = [
                    r[0] for r in session.query(RequestRecord.response_time_ms)
                    .filter(RequestRecord.timestamp >= since)
                    .filter(RequestRecord.route_pattern == route)
                    .filter(RequestRecord.method == method)
                    .order_by(RequestRecord.response_time_ms)
                    .all()
                ]
                if times:
                    n = len(times)

                    def pct(p: int) -> float:
                        return round(times[min(int(n * p / 100), n - 1)], 2)

                    results.append({
                        "route": route,
                        "method": method,
                        "count": n,
                        "p50": pct(50),
                        "p90": pct(90),
                        "p95": pct(95),
                        "p99": pct(99),
                    })
            return results

    def get_error_rate_by_hour(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get error rate trend by hour to detect spikes."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp).label("hour"),
                    func.count(RequestRecord.id).label("total"),
                    func.sum(case((RequestRecord.is_error == True, 1), else_=0)).label("errors"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp))
                .order_by(func.strftime("%Y-%m-%d %H:00", RequestRecord.timestamp))
                .all()
            )
            return [
                {
                    "hour": r[0],
                    "total": r[1],
                    "errors": r[2],
                    "error_rate": round((r[2] / r[1] * 100) if r[1] > 0 else 0, 2),
                }
                for r in results
            ]

    def get_top_routes_by_traffic(self, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
        """Get top routes by request volume."""
        since = datetime.utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            from sqlalchemy import func
            results = (
                session.query(
                    RequestRecord.route_pattern,
                    RequestRecord.method,
                    func.count(RequestRecord.id).label("hits"),
                    func.avg(RequestRecord.response_time_ms).label("avg_ms"),
                    func.sum(case((RequestRecord.is_error == True, 1), else_=0)).label("errors"),
                )
                .filter(RequestRecord.timestamp >= since)
                .group_by(RequestRecord.route_pattern, RequestRecord.method)
                .order_by(func.count(RequestRecord.id).desc())
                .limit(limit)
                .all()
            )
            total_hits = sum(r[2] for r in results) or 1
            return [
                {
                    "route": r[0],
                    "method": r[1],
                    "hits": r[2],
                    "traffic_share_pct": round(r[2] / total_hits * 100, 2),
                    "avg_response_time_ms": round(r[3], 2) if r[3] else 0,
                    "error_rate": round((r[4] / r[2] * 100) if r[2] > 0 else 0, 2),
                }
                for r in results
            ]

    def clear_data(self):
        """Clear all stored data."""
        with self.Session() as session:
            session.query(RequestRecord).delete()
            session.query(RouteStats).delete()
            session.commit()

    def close(self):
        """Close database connection."""
        self.engine.dispose()
