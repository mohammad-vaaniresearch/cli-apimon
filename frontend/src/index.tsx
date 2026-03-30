import * as React from "react";
import { useState, useEffect } from "react";
import { render, Box, Text, useInput } from "ink";
import axios from "axios";

interface Route {
  route_pattern: string;
  method: string;
  hit_count: number;
  avg_response_time_ms: number;
  min_response_time_ms: number;
  max_response_time_ms: number;
  error_count: number;
  error_rate: number;
}

interface Request {
  id: number;
  method: string;
  path: string;
  response_status: number;
  response_time_ms: number;
  timestamp: string;
  is_error: boolean;
}

interface Analytics {
  total_requests: number;
  error_requests: number;
  error_rate: number;
  unique_routes: number;
  avg_response_time_ms: number;
}

interface Suggestion {
  severity: string;
  category: string;
  message: string;
  details?: string;
}

const API_BASE = process.env.APIMON_PORT
  ? `http://localhost:${process.env.APIMON_PORT}`
  : "http://localhost:8080";

const truncate = (str: string, len: number) =>
  str.length > len ? str.slice(0, len) + "..." : str;

const SpinnerScreen: React.FC<{ message: string }> = ({ message }) => (
  <Box>
    <Text color="yellow">⠋</Text>
    <Text> {message}</Text>
  </Box>
);

const ErrorScreen: React.FC<{ error: string }> = ({ error }) => (
  <Box flexDirection="column" padding={1}>
    <Text color="red" bold>
      Error: {error}
    </Text>
    <Text dimColor>
      Make sure the proxy is running: apimon proxy
    </Text>
  </Box>
);

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [requests, setRequests] = useState<Request[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [tab, setTab] = useState<"dashboard" | "routes" | "requests">("dashboard");

  useInput((input: string) => {
    if (input === "1") setTab("dashboard");
    if (input === "2") setTab("routes");
    if (input === "3") setTab("requests");
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [analyticsRes, routesRes, requestsRes, suggestionsRes] = await Promise.all([
          axios.get(`${API_BASE}/_apimon/analytics`),
          axios.get(`${API_BASE}/_apimon/stats`),
          axios.get(`${API_BASE}/_apimon/requests?limit=15`),
          axios.get(`${API_BASE}/_apimon/suggestions`),
        ]);
        setAnalytics(analyticsRes.data);
        setRoutes(routesRes.data);
        setRequests(requestsRes.data);
        setSuggestions(suggestionsRes.data);
        setLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch data");
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !analytics) {
    return <SpinnerScreen message="Loading apimon dashboard..." />;
  }

  if (error && !analytics) {
    return <ErrorScreen error={error} />;
  }

  return (
    <Box flexDirection="column">
      <Box borderStyle="bold" borderColor="cyan" paddingX={1}>
        <Text bold color="cyan">
          🚀 apimon - API Monitor
        </Text>
        <Box paddingLeft={20}>
          <Text dimColor>Live (3s)</Text>
        </Box>
      </Box>

      <Box flexDirection="row" paddingY={1}>
        <Text color={tab === "dashboard" ? "magenta" : "white"} bold={tab === "dashboard"}>
          [1] Dashboard  
        </Text>
        <Text>  </Text>
        <Text color={tab === "routes" ? "magenta" : "white"} bold={tab === "routes"}>
          [2] Routes  
        </Text>
        <Text>  </Text>
        <Text color={tab === "requests" ? "magenta" : "white"} bold={tab === "requests"}>
          [3] Requests
        </Text>
      </Box>

      {tab === "dashboard" && analytics && (
        <Box flexDirection="column">
          <Box flexDirection="row" gap={2}>
            <Box borderStyle="round" borderColor="green" paddingX={1} width={22} flexDirection="column">
              <Text bold>Total Hits</Text>
              <Text color="green">{analytics.total_requests}</Text>
            </Box>
            <Box borderStyle="round" borderColor="red" paddingX={1} width={22} flexDirection="column">
              <Text bold>Error Rate</Text>
              <Text color="red">{analytics.error_rate.toFixed(1)}%</Text>
            </Box>
            <Box borderStyle="round" borderColor="yellow" paddingX={1} width={22} flexDirection="column">
              <Text bold>Avg Latency</Text>
              <Text color="yellow">{analytics.avg_response_time_ms.toFixed(0)}ms</Text>
            </Box>
            <Box borderStyle="round" borderColor="cyan" paddingX={1} width={22} flexDirection="column">
              <Text bold>Endpoints</Text>
              <Text color="cyan">{analytics.unique_routes}</Text>
            </Box>
          </Box>

          <Box flexDirection="column" marginTop={1} borderStyle="single" borderColor="dim" paddingX={1}>
            <Text bold dimColor>💡 PATTERNS & SUGGESTIONS</Text>
            {suggestions.length === 0 ? (
              <Text color="green">  ✅ No issues detected. API performance is healthy.</Text>
            ) : (
              suggestions.slice(0, 6).map((s: Suggestion, i: number) => {
                const emoji = s.severity === "high" ? "🔴" : s.severity === "medium" ? "🟡" : "🟢";
                const color = s.severity === "high" ? "red" : s.severity === "medium" ? "yellow" : "green";
                return (
                  <Box key={i} flexDirection="column">
                    <Text color={color}>
                      {emoji} {s.message}
                    </Text>
                    {s.details && <Text dimColor>    └ {s.details}</Text>}
                  </Box>
                );
              })
            )}
          </Box>
        </Box>
      )}

      {tab === "routes" && (
        <Box flexDirection="column" borderStyle="single" paddingX={1}>
          <Box flexDirection="row" gap={2}>
            <Box width={8}><Text bold>METHOD</Text></Box>
            <Box width={40}><Text bold>ROUTE PATTERN</Text></Box>
            <Box width={10} flexDirection="row" justifyContent="flex-end"><Text bold>HITS</Text></Box>
            <Box width={10} flexDirection="row" justifyContent="flex-end"><Text bold>AVG MS</Text></Box>
            <Box width={10} flexDirection="row" justifyContent="flex-end"><Text bold>ERR %</Text></Box>
          </Box>
          <Text dimColor>{"─".repeat(82)}</Text>
          {routes.slice(0, 15).map((route: Route, i: number) => (
            <Box key={i} flexDirection="row" gap={2}>
              <Box width={8}><Text color="cyan">{route.method}</Text></Box>
              <Box width={40}><Text>{truncate(route.route_pattern, 40)}</Text></Box>
              <Box width={10} flexDirection="row" justifyContent="flex-end"><Text color="green">{route.hit_count}</Text></Box>
              <Box width={10} flexDirection="row" justifyContent="flex-end"><Text color="yellow">{route.avg_response_time_ms.toFixed(0)}</Text></Box>
              <Box width={10} flexDirection="row" justifyContent="flex-end"><Text color="red">{route.error_rate.toFixed(0)}%</Text></Box>
            </Box>
          ))}
        </Box>
      )}

      {tab === "requests" && (
        <Box flexDirection="column" borderStyle="single" paddingX={1}>
          <Box flexDirection="row" gap={2}>
            <Box width={8}><Text bold>METHOD</Text></Box>
            <Box width={40}><Text bold>PATH</Text></Box>
            <Box width={8} flexDirection="row" justifyContent="flex-end"><Text bold>STATUS</Text></Box>
            <Box width={10} flexDirection="row" justifyContent="flex-end"><Text bold>TIME</Text></Box>
          </Box>
          <Text dimColor>{"─".repeat(70)}</Text>
          {requests.length === 0 ? (
            <Text dimColor>Waiting for requests...</Text>
          ) : (
            requests.map((req: Request, i: number) => (
              <Box key={i} flexDirection="row" gap={2}>
                <Box width={8}><Text color="cyan">{req.method}</Text></Box>
                <Box width={40}><Text>{truncate(req.path, 40)}</Text></Box>
                <Box width={8} flexDirection="row" justifyContent="flex-end">
                  <Text color={req.response_status >= 400 ? "red" : "green"}>
                    {req.response_status}
                  </Text>
                </Box>
                <Box width={10} flexDirection="row" justifyContent="flex-end"><Text color="yellow">{req.response_time_ms.toFixed(0)}ms</Text></Box>
              </Box>
            ))
          )}
          <Box marginTop={1}>
            <Text dimColor>Detail: apimon request [id]</Text>
          </Box>
        </Box>
      )}

      <Box marginTop={1}>
        <Text dimColor>Press 1, 2, or 3 to switch tabs • Ctrl+C to exit</Text>
      </Box>
    </Box>
  );
};

const generateSuggestions = (routes: Route[], analytics: Analytics): Suggestion[] => {
  const suggestions: Suggestion[] = [];

  if (analytics.error_rate > 10) {
    suggestions.push({
      severity: "high",
      category: "errors",
      message: `Overall error rate is ${analytics.error_rate.toFixed(1)}%`,
    });
  }

  if (analytics.avg_response_time_ms > 500) {
    suggestions.push({
      severity: "medium",
      category: "performance",
      message: `Avg response time is ${analytics.avg_response_time_ms.toFixed(0)}ms`,
    });
  }

  const slowRoutes = routes.filter((r) => r.avg_response_time_ms > 1000);
  if (slowRoutes.length > 0) {
    suggestions.push({
      severity: "medium",
      category: "performance",
      message: `${slowRoutes.length} routes have slow response times`,
    });
  }

  const errorRoutes = routes.filter((r) => r.error_rate > 20);
  for (const route of errorRoutes) {
    suggestions.push({
      severity: "high",
      category: "errors",
      message: `Route ${route.route_pattern} has ${route.error_rate.toFixed(0)}% error rate`,
    });
  }

  return suggestions;
};

render(<Dashboard />);
