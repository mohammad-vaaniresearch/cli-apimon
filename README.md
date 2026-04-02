# apimon

A pip-installable CLI tool for API monitoring, analytics, and AI-powered improvement insights using LLM integration (OpenAI, Gemini, Anthropic).

## Features

- **Proxy-based Monitoring**: Sits between clients and your API server to capture all traffic
- **Hit Count Tracking**: See which routes are most frequently accessed
- **Request/Response Capture**: Full details of every request and response
- **Analytics Dashboard**: Rich terminal UI showing performance metrics
- **Advanced Pattern Detection**: Automatically suggests improvements for 'chatty' APIs, slow writes, and security anomalies
- **ASCII Graphs**: Visualize request activity over time via CLI
- **LLM-Powered Insights**: Generate AI-driven improvement suggestions using OpenAI, Google Gemini, or Anthropic Claude
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

4. **Generate AI-powered insights** (requires API key):

```bash
# Set your API key
export OPENAI_API_KEY="your-key-here"

# Generate insights
apimon insights --provider openai
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
| `apimon insights` | Generate LLM-powered AI insights |
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

### LLM Insights Command

The `insights` command generates AI-powered analysis of your API analytics data:

```bash
# Using OpenAI (default)
apimon insights

# Using Google Gemini
apimon insights --provider gemini

# Using Anthropic Claude
apimon insights --provider anthropic

# Specify a custom model
apimon insights --model gpt-4o

# Analyze different time range
apimon insights --hours 48
```

## LLM Providers

### OpenAI

Set the API key via environment variable or CLI option:

```bash
export OPENAI_API_KEY="sk-..."
apimon insights --provider openai
```

### Google Gemini

```bash
export GEMINI_API_KEY="your-gemini-key"
apimon insights --provider gemini
```

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
apimon insights --provider anthropic
```

## Architecture

- **Python Backend**: Proxy server using aiohttp, data storage with SQLite/SQLAlchemy
- **Textual UI**: Pure Python TUI for interactive dashboards
- **LLM Integration**: Optional integration with OpenAI, Gemini, or Anthropic for AI-powered insights

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
- `OPENAI_API_KEY`: OpenAI API key for LLM insights
- `GEMINI_API_KEY`: Google Gemini API key for LLM insights
- `ANTHROPIC_API_KEY`: Anthropic API key for LLM insights

## Development

```bash
# Install in development mode
pip install -e ".[dev,llm]"

# Run the proxy
apimon proxy --target-port 3000

# Run the UI
apimon ui

# Or use the dashboard
apimon dashboard
```

## License

MIT
