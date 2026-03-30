import pytest
from apimon.storage import DataStore
from apimon.analytics import AnalyticsEngine

def test_generate_suggestions(tmp_path):
    db_path = tmp_path / "test_analytics.db"
    store = DataStore(str(db_path))
    engine = AnalyticsEngine(store)
    
    # No data -> no suggestions
    assert len(engine.generate_suggestions()) == 0
    
    # Add slow route
    store.save_request("GET", "/slow", "", {}, None, 200, {}, "", 2500.0, "/slow")
    
    suggestions = engine.generate_suggestions()
    assert len(suggestions) > 0
    categories = [s.category for s in suggestions]
    assert "performance" in categories
    assert any("slow response" in s.message.lower() for s in suggestions)

def test_graph_data(tmp_path):
    db_path = tmp_path / "test_graph.db"
    store = DataStore(str(db_path))
    engine = AnalyticsEngine(store)
    
    store.save_request("GET", "/", "", {}, None, 200, {}, "", 10.0)
    
    graph = engine.get_graph_data(hours=1)
    assert "time_series" in graph
    assert len(graph["time_series"]) >= 1
    assert graph["time_series"][0]["hits"] == 1
