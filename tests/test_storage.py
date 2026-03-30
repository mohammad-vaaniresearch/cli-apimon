import pytest
from datetime import datetime
from apimon.storage import DataStore, RequestRecord, RouteStats

def test_save_request(tmp_path):
    db_path = tmp_path / "test.db"
    store = DataStore(str(db_path))
    
    req_id = store.save_request(
        method="GET",
        path="/users/123",
        query_string="a=b",
        request_headers={"User-Agent": "test"},
        request_body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"id": 123}',
        response_time_ms=50.5,
        route_pattern="/users/{id}"
    )
    
    assert req_id == 1
    
    # Check record
    detail = store.get_request_detail(req_id)
    assert detail["method"] == "GET"
    assert detail["path"] == "/users/123"
    assert detail["response_status"] == 200
    assert detail["route_pattern"] == "/users/{id}"
    
    # Check stats
    stats = store.get_route_stats()
    assert len(stats) == 1
    assert stats[0]["route_pattern"] == "/users/{id}"
    assert stats[0]["hit_count"] == 1
    assert stats[0]["avg_response_time_ms"] == 50.5

def test_error_tracking(tmp_path):
    db_path = tmp_path / "test_error.db"
    store = DataStore(str(db_path))
    
    store.save_request("POST", "/api/data", "", {}, None, 500, {}, "Error", 10.0, "/api/data")
    
    analytics = store.get_analytics_summary()
    assert analytics["total_requests"] == 1
    assert analytics["error_requests"] == 1
    assert analytics["error_rate"] == 100.0

def test_clear_data(tmp_path):
    db_path = tmp_path / "test_clear.db"
    store = DataStore(str(db_path))
    
    store.save_request("GET", "/", "", {}, None, 200, {}, "", 1.0)
    assert store.get_analytics_summary()["total_requests"] == 1
    
    store.clear_data()
    assert store.get_analytics_summary()["total_requests"] == 0
