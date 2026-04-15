"""LLM integration module for generating AI-powered insights from analytics data."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel

from apimon.storage import DataStore


console = Console()


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


@dataclass
class LLMInsight:
    """Represents an LLM-generated insight."""

    title: str
    description: str
    category: str
    priority: str  # "high", "medium", "low"
    action_items: list[str]


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate_insight(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Generate insight from prompt."""
        pass

    @property
    @abstractmethod
    def provider(self) -> LLMProvider:
        """Return the provider type."""
        pass


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass --api-key")

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OPENAI

    def generate_insight(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an API performance expert. Analyze the provided analytics data and provide actionable insights for improving API performance, reliability, and efficiency."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content


class GeminiClient(LLMClient):
    """Google Gemini API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key required. Set GEMINI_API_KEY environment variable or pass --api-key")

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.GEMINI

    def generate_insight(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        from google import genai

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=model or "gemini-2.0-flash",
            contents=prompt,
            config={
                "system_instruction": "You are an API performance expert. Analyze the provided analytics data and provide actionable insights for improving API performance, reliability, and efficiency.",
                "temperature": 0.7,
                "max_output_tokens": 1500,
            }
        )
        return response.text


class AnthropicClient(LLMClient):
    """Anthropic Claude API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY environment variable or pass --api-key")

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.ANTHROPIC

    def generate_insight(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=model or "claude-3-5-haiku-20241022",
            max_tokens=1500,
            system="You are an API performance expert. Analyze the provided analytics data and provide actionable insights for improving API performance, reliability, and efficiency.",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
        )
        return response.content[0].text


def create_llm_client(
    provider: LLMProvider,
    api_key: Optional[str] = None,
) -> LLMClient:
    """Factory function to create an LLM client."""
    if provider == LLMProvider.OPENAI:
        return OpenAIClient(api_key)
    elif provider == LLMProvider.GEMINI:
        return GeminiClient(api_key)
    elif provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def format_analytics_prompt(
    store: DataStore,
    hours: int = 24,
) -> str:
    """Format analytics data into a comprehensive prompt for the LLM."""
    summary = store.get_analytics_summary()
    stats = store.get_route_stats()
    top_routes = store.get_top_routes_by_traffic(hours=hours, limit=10)
    error_messages = store.get_unique_error_messages(hours=hours, limit=15)
    cache_candidates = store.get_cache_candidates(hours=hours)
    percentiles = store.get_response_time_percentiles(hours=hours)
    route_percentiles = store.get_route_percentiles(hours=hours, limit=8)
    error_trend = store.get_error_rate_by_hour(hours=hours)

    prompt = f"""Analyze the following API monitoring data from the last {hours} hours and provide actionable insights.

## Overall Analytics Summary
- Total Requests: {summary['total_requests']:,}
- Error Rate: {summary['error_rate']:.1f}%
- Average Response Time: {summary['avg_response_time_ms']:.0f}ms
- Unique Routes: {summary['unique_routes']}

## Response Time Percentiles (Global)
- p50: {percentiles['p50']}ms
- p90: {percentiles['p90']}ms
- p95: {percentiles['p95']}ms
- p99: {percentiles['p99']}ms
- Sample size: {percentiles['sample_size']:,}

## Top Routes by Traffic Volume
"""
    for r in top_routes:
        prompt += f"- {r['method']} {r['route']}: {r['hits']:,} hits ({r['traffic_share_pct']}% of traffic), avg {r['avg_response_time_ms']}ms, {r['error_rate']}% errors\n"

    prompt += """
## Route-Level Latency Percentiles
"""
    for r in route_percentiles:
        prompt += f"- {r['method']} {r['route']} (n={r['count']}): p50={r['p50']}ms, p90={r['p90']}ms, p95={r['p95']}ms, p99={r['p99']}ms\n"

    prompt += """
## Unique Error Messages (Top 15)
"""
    if error_messages:
        for e in error_messages:
            body_preview = (e['error_body'] or "")[:200].replace('\n', ' ')
            prompt += f"- {e['method']} {e['route']} -> {e['status_code']} (x{e['count']}): {body_preview}\n"
    else:
        prompt += "- No error response bodies captured\n"

    prompt += """
## Caching Candidates (GET routes with <10% error rate, sorted by cache benefit)
"""
    if cache_candidates:
        for c in cache_candidates:
            prompt += f"- {c['route']}: {c['hits']:,} hits, avg {c['avg_response_time_ms']}ms, benefit_score={c['cache_benefit_score']}\n"
    else:
        prompt += "- No strong caching candidates identified\n"

    prompt += """
## Error Rate Trend by Hour
"""
    for h in error_trend[-6:]:
        prompt += f"- {h['hour']}: {h['total']} requests, {h['errors']} errors ({h['error_rate']}%)\n"

    prompt += """
## Route Statistics (All Routes)
"""
    for route in stats:
        prompt += f"- {route['method']} {route['route_pattern']}: {route['hit_count']} hits, avg {route['avg_response_time_ms']:.0f}ms (min {route['min_response_time_ms']:.0f}ms, max {route['max_response_time_ms']:.0f}ms), {route['error_count']} errors ({route['error_rate']:.1f}%)\n"

    prompt += """
---

Based on this data, provide:

1. **Critical Issues** - What needs immediate attention? (high error rates, broken endpoints, security concerns)

2. **Performance Bottlenecks** - Which routes are slow? What do the p95/p99 latencies suggest? Are there outliers?

3. **Caching Strategy** - Based on the cache candidates and traffic patterns, what should be cached? Suggest TTLs and cache invalidation strategies.

4. **Error Analysis** - What do the error messages reveal? Are there patterns (auth failures, missing resources, method not allowed)?

5. **Architecture Recommendations** - Based on traffic distribution and latency patterns, what architectural changes would help? (rate limiting, async processing, database optimization, etc.)

6. **Prioritized Action Items** - List 5-7 specific, actionable improvements in priority order with expected impact.

Be specific and reference the actual data. Avoid generic advice.
"""

    return prompt


class LLMInsightGenerator:
    """Generate insights from analytics data using LLM."""

    def __init__(self, store: DataStore, client: LLMClient):
        self.store = store
        self.client = client

    def generate_insights(
        self,
        hours: int = 24,
        model: Optional[str] = None,
    ) -> str:
        """Generate LLM-powered insights from analytics data."""
        console.print("[cyan]Generating insights...[/cyan]")

        prompt = format_analytics_prompt(self.store, hours)

        try:
            response = self.client.generate_insight(prompt, model)
            return response
        except Exception as e:
            return f"Error generating insights: {str(e)}"

    def print_insights(self, insights: str):
        """Print insights in a rich-formatted panel."""
        console.print(Panel(
            insights,
            title="🤖 LLM-Powered Insights",
            border_style="green",
            expand=False,
        ))


def try_create_llm_client(
    provider: LLMProvider,
    api_key: Optional[str] = None,
) -> Optional[LLMClient]:
    """Create an LLM client, returning None if the key is missing or invalid."""
    try:
        return create_llm_client(provider, api_key)
    except (ValueError, ImportError):
        return None


def get_provider_choices() -> list[str]:
    """Return list of available providers for CLI."""
    return [p.value for p in LLMProvider]
