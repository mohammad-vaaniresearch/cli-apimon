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
    """Format analytics data into a prompt for the LLM."""
    summary = store.get_analytics_summary()
    stats = store.get_route_stats()
    requests = store.get_recent_requests(limit=100)

    prompt = f"""Analyze the following API monitoring data from the last {hours} hours and provide insights:

## Overall Analytics Summary
- Total Requests: {summary['total_requests']}
- Error Rate: {summary['error_rate']:.1f}%
- Average Response Time: {summary['avg_response_time_ms']:.0f}ms
- Unique Routes: {summary['unique_routes']}

## Route Statistics (Top 15)
"""
    for route in stats[:15]:
        prompt += f"""
- {route['method']} {route['route_pattern']}:
  Hits: {route['hit_count']}, Avg: {route['avg_response_time_ms']:.0f}ms,
  Min: {route['min_response_time_ms']:.0f}ms, Max: {route['max_response_time_ms']:.0f}ms,
  Errors: {route['error_count']} ({route['error_rate']:.1f}%)
"""

    prompt += f"""
## Recent Requests (Last 20)
"""
    for req in requests[:20]:
        status = "ERROR" if req['is_error'] else "OK"
        prompt += f"- {req['method']} {req['path']} -> {req['response_status']} ({req['response_time_ms']:.0f}ms) [{status}]\n"

    prompt += """
Please analyze this data and provide:
1. Key performance bottlenecks or issues
2. Patterns that suggest architectural improvements
3. Security concerns (if any)
4. Prioritized action items for improving the API

Format your response with clear sections and prioritize the most impactful improvements.
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


def get_provider_choices() -> list[str]:
    """Return list of available providers for CLI."""
    return [p.value for p in LLMProvider]
