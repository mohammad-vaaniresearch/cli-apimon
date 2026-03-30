# apimon

A pip-installable CLI tool for API monitoring, analytics, and route improvement suggestions.

## Features

- **Proxy-based Monitoring**: Sits between clients and your API server to capture all traffic
- **Hit Count Tracking**: See which routes are most frequently accessed
- **Request/Response Capture**: Full details of every request and response
- **Analytics Dashboard**: Rich terminal UI showing performance metrics
- **Advanced Pattern Detection**: Automatically suggests improvements for 'chatty' APIs, slow writes, and security anomalies
- **ASCII Graphs**: Visualize request activity over time via CLI
- **Dual UI**: React+Ink UI for live monitoring, Textual fallback for pure Python
- **Automated Testing**: Comprehensive test suite for storage and analytics

## Installation

```bash
pip install apimon
```

## Quick Start

1. **Start the proxy server** (forwarding to your API on port 3000):

```bash
apimon proxy --target-port 3000
```

2. **In another terminal**, make some API requests to `http://localhost:8080` (the proxy):

```bash
curl http://localhost:8080/api/users
```

3. **View the dashboard**:

```bash
apimon dashboard
```

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `apimon proxy` | Start the proxy server for monitoring |
| `apimon dashboard` | Show analytics dashboard |
| `apimon stats` | Show route statistics |
| `apimon requests` | Show recent requests |
| `apimon request <id>` | Show detailed view of a request |
| `apimon suggestions` | Show improvement suggestions |
| `apimon graph` | Show ASCII graphs of activity |
| `apimon ui` | Launch interactive TUI |
| `apimon export` | Export data to JSON |
| `apimon clear` | Clear all stored data |

### Proxy Options

```bash
apimon proxy --target-host localhost --target-port 3000 --port 8080
```

- `--target-host`: Your API server host (default: localhost)
- `--target-port`: Your API server port (default: 3000)
- `--port`: Proxy listen port (default: 8080)
- `--db-path`: Path to SQLite database (default: apimon.db)

### Dashboard Options

```bash
apimon dashboard
apimon stats --hours 24
apimon requests --limit 50
apimon suggestions
```

## Architecture

- **Python Backend**: Proxy server using aiohttp, data storage with SQLite/SQLAlchemy
- **Node.js Frontend**: React+Ink CLI UI for interactive dashboards
- **Textual Fallback**: Pure Python TUI when Node.js is unavailable

### Data Storage

All data is stored in a local SQLite database (`apimon.db` by default). The schema includes:

- `requests`: Individual request/response records
- `route_stats`: Aggregated statistics per route

### Route Pattern Extraction

The proxy automatically normalizes routes like:
- `/users/123` → `/users/{id}`
- `/posts/abc123` → `/posts/{id}`

This allows aggregating statistics for parameterized routes.

## Environment Variables

- `APIMON_PORT`: Port for the proxy server (default: 8080)
- `APIMON_DB_PATH`: Path to database file

## Development

```bash
# Install in development mode
pip install -e .

# Install frontend dependencies
cd frontend && npm install

# Run the proxy
apimon proxy --target-port 3000

# Run the UI
apimon ui

# Or use the Textual UI directly
apimon dashboard
```

## License

MIT
# cli-apimon
