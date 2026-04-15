# apimon

A CLI tool for API monitoring, analytics, and AI-powered improvement insights. Designed for both humans and AI agents.

## Features

- **Proxy-based Monitoring**: Sits between clients and your API server to capture all traffic
- **Rich Analytics**: Hit counts, response times, error rates, percentiles (p50/p90/p95/p99)
- **Pattern Detection**: Automatically identifies slow routes, chatty APIs, caching opportunities, and security anomalies
- **LLM-Powered Insights**: Generate AI-driven analysis using OpenAI, Google Gemini, or Anthropic Claude
- **Agent-Friendly**: Full `--json` support and `--ai` mode for non-interactive automation
- **Interactive TUI**: Textual-based terminal UI for live monitoring

## Installation

```bash
pip install apimon
```

For LLM integration (optional):

```bash
pip install apimon[llm]
```

## Quick Start

### 1. Start the proxy server

```bash
apimon proxy --target-port 3000
```

### 2. Make requests through the proxy

```bash
curl http://localhost:8080/api/users
```

### 3. View analytics

```bash
# Human-friendly dashboard
apimon dashboard

# Or interactive TUI
apimon ui
```

### 4. Generate AI insights

```bash
export OPENAI_API_KEY="sk-..."
apimon insights --provider openai
```

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `apimon proxy` | Start the proxy server |
| `apimon ui` | Interactive TUI dashboard |
| `apimon ui --ai` | **Machine-readable JSON snapshot** |
| `apimon dashboard` | Terminal analytics dashboard |
| `apimon stats` | Route statistics |
| `apimon requests` | Recent requests |
| `apimon request <id>` | Detailed view of a request |
| `apimon suggestions` | Rule-based improvement suggestions |
| `apimon insights` | LLM-powered AI analysis |
| `apimon graph` | ASCII graphs of activity |
| `apimon export <file>` | Export data to JSON file |
| `apimon clear` | Clear all stored data |

---

## AI Agent Integration

apimon is designed to be used by AI agents. Every command supports `--json` output, and `apimon ui --ai` provides a complete snapshot for automated analysis.

### Non-Interactive Mode (`--ai`)

```bash
# Get full analytics snapshot as JSON (no TUI)
apimon ui --ai

# Include LLM analysis
apimon ui --ai --provider openai

# Pipe to jq for specific fields
apimon ui --ai | jq .analytics_summary
apimon ui --ai | jq .cache_candidates
apimon ui --ai | jq .unique_error_messages
```

### JSON Output Fields

The `--ai` mode returns a comprehensive JSON object:

```json
{
  "apimon_version": "0.1.0",
  "db_path": "apimon.db",
  "hours_analyzed": 24,
  "analytics_summary": {
    "total_requests": 8158,
    "error_rate": 48.1,
    "avg_response_time_ms": 26.15,
    "unique_routes": 7
  },
  "response_time_percentiles": {
    "p50": 1.16,
    "p90": 96.52,
    "p95": 123.33,
    "p99": 146.41
  },
  "route_stats": [...],
  "top_routes_by_traffic": [...],
  "route_percentiles": [...],
  "status_code_distribution": [...],
  "method_distribution": [...],
  "error_summary": [...],
  "unique_error_messages": [...],
  "slowest_routes": [...],
  "cache_candidates": [...],
  "hourly_summary": [...],
  "error_rate_trend": [...],
  "suggestions": [...],
  "llm_prompt": "...",
  "llm_provider": "openai",
  "llm_insights": "...",
  "llm_error": null
}
```

### Key Fields for Agents

| Field | Description |
|-------|-------------|
| `analytics_summary` | Overall stats: total requests, error rate, avg response time |
| `response_time_percentiles` | Global p50, p90, p95, p99 latencies |
| `top_routes_by_traffic` | Routes ranked by hit count with traffic share % |
| `route_percentiles` | Per-route latency percentiles |
| `unique_error_messages` | Actual error response bodies grouped by route/status |
| `cache_candidates` | GET routes suitable for caching, with benefit scores |
| `error_rate_trend` | Hourly error rates to detect spikes |
| `suggestions` | Rule-based improvement suggestions |
| `llm_prompt` | The exact prompt sent to the LLM (for debugging/reuse) |
| `llm_insights` | LLM response (if `--provider` was specified) |

### JSON Mode for Individual Commands

```bash
# Route statistics
apimon stats --json
apimon stats --json | jq '.[] | select(.error_rate > 10)'

# Recent requests
apimon requests --json --limit 100
apimon requests --json --method POST | jq '.[] | select(.response_status >= 400)'

# Single request detail
apimon request 42 --json

# Suggestions
apimon suggestions --json
apimon suggestions --json | jq '.[] | select(.severity == "high")'

# LLM insights
apimon insights --json --provider openai
apimon insights --json --provider openai | jq -r .insights

# Graph data
apimon graph --json
apimon graph --json | jq .time_series
```

### Example: Agent Workflow

```bash
# 1. Get full snapshot
DATA=$(apimon ui --ai --provider openai)

# 2. Check for critical issues
echo "$DATA" | jq '.suggestions[] | select(.severity == "high")'

# 3. Get caching recommendations
echo "$DATA" | jq '.cache_candidates'

# 4. Read LLM analysis
echo "$DATA" | jq -r '.llm_insights'

# 5. Get the prompt for custom LLM calls
echo "$DATA" | jq -r '.llm_prompt' > prompt.txt
```

---

## LLM Providers

### Environment Variables

| Provider | Environment Variable |
|----------|---------------------|
| OpenAI | `OPENAI_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |

### Usage

```bash
# OpenAI (default)
export OPENAI_API_KEY="sk-..."
apimon insights --provider openai
apimon ui --ai --provider openai

# Google Gemini
export GEMINI_API_KEY="..."
apimon insights --provider gemini

# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
apimon insights --provider anthropic

# Pass key directly (not recommended for scripts)
apimon insights --provider openai --api-key sk-...
```

### LLM Prompt Contents

The LLM receives comprehensive data including:

- Overall analytics summary
- Response time percentiles (global and per-route)
- Traffic distribution by route
- Unique error messages with response bodies
- Caching candidates with benefit scores
- Error rate trends by hour
- Full route statistics

The prompt asks for:
1. Critical issues requiring immediate attention
2. Performance bottlenecks analysis
3. Caching strategy with TTL recommendations
4. Error pattern analysis
5. Architecture recommendations
6. Prioritized action items

---

## Interactive TUI

```bash
apimon ui
```

On startup, you'll be prompted to configure an LLM provider (optional). Press **Skip** to use the TUI without LLM features.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Routes tab |
| `2` | Requests tab |
| `3` | Analytics tab |
| `r` | Refresh data |
| `d` | Toggle dark mode |
| `q` | Quit |

The Analytics tab includes a **"Get LLM Insights"** button that calls the configured LLM and displays results inline.

---

## Proxy Options

```bash
apimon proxy --target-host localhost --target-port 3000 --port 8080
```

| Option | Default | Description |
|--------|---------|-------------|
| `--target-host` | `localhost` | Your API server host |
| `--target-port` | `3000` | Your API server port |
| `--port` | `8080` | Proxy listen port |
| `--db-path` | `apimon.db` | SQLite database path |

---

## Data Storage

All data is stored in a local SQLite database (`apimon.db` by default).

### Route Pattern Normalization

The proxy automatically normalizes parameterized routes:

- `/users/123` → `/users/{id}`
- `/posts/abc-def-123` → `/posts/{id}`
- `/api/v2/items` → `/api/{version}/items`

This enables meaningful aggregation of statistics.

### Clear Data

```bash
apimon clear --yes  # Non-interactive (for scripts/agents)
apimon clear        # Prompts for confirmation
```

---

## License

MIT
