"""Time aur mausam wale tools."""

from datetime import datetime

import requests
from anthropic import beta_tool


@beta_tool
def get_time() -> str:
    """Get the current local date and time."""
    return datetime.now().strftime("%A, %d %B %Y, %I:%M %p")


@beta_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. Karachi or Lahore.
    """
    try:
        # wttr.in free hai, koi API key nahi chahiye
        resp = requests.get(f"https://wttr.in/{city}", params={"format": "%C, %t, humidity %h, wind %w"}, timeout=10)
        resp.raise_for_status()
        return f"{city}: {resp.text.strip()}"
    except requests.RequestException as e:
        return f"Weather service se data nahi mila: {e}"
