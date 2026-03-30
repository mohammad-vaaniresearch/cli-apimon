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

    def clear_data(self):
        """Clear all stored data."""
        with self.Session() as session:
            session.query(RequestRecord).delete()
            session.query(RouteStats).delete()
            session.commit()

    def close(self):
        """Close database connection."""
        self.engine.dispose()
