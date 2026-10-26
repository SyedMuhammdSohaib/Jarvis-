"""Computer control wale tools: apps aur websites kholna."""

import platform
import subprocess
import webbrowser
from urllib.parse import quote_plus

from anthropic import beta_tool


@beta_tool
def open_app(name: str) -> str:
    """Open an application on the user's computer.

    Args:
        name: App name, e.g. "notepad", "calc", "chrome", "code" (VS Code), "spotify".
    """
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(f'start "" "{name}"', shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        return f"Opened {name}."
    except (OSError, subprocess.SubprocessError) as e:
        return f"Could not open {name}: {e}"


@beta_tool
def open_website(url: str) -> str:
    """Open a website in the default browser.

    Args:
        url: Full URL or domain, e.g. "youtube.com".
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


@beta_tool
def search_google(query: str) -> str:
    """Search Google for something and open the results in the browser.

    Args:
        query: What to search for.
    """
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"Searched Google for: {query}"
