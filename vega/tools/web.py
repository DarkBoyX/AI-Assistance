"""Web search, browsing and reading pages."""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.parse
import webbrowser

import httpx

from .base import P, tool

_ENGINES = {"google": "https://www.google.com/search?q=", "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=", "youtube": "https://www.youtube.com/results?search_query=",
            "maps": "https://www.google.com/maps/search/", "images": "https://www.google.com/search?tbm=isch&q="}
_APP_SCHEMES = {"ms-settings", "discord", "whatsapp", "spotify", "steam", "slack", "tg", "msteams", "mailto",
                "zoommtg", "ms-screenclip", "microsoft-edge"}
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def _browser_exe(name: str) -> str | None:
    from .apps import _app_paths_registry
    import shutil
    n = name.lower().replace("google ", "").replace(" browser", "").strip()
    return _app_paths_registry(n) or shutil.which(n)


def open_in_browser(url: str, browser: str = "") -> None:
    if browser:
        exe = _browser_exe(browser)
        if exe:
            subprocess.Popen([exe, url])
            return
    webbrowser.open(url)


@tool("Open a web search in the user's browser (Google by default; also bing, duckduckgo, youtube, maps, images).",
      {"query": P("string", "What to search for"), "engine": P("string", "Search site", enum=list(_ENGINES)),
       "browser": P("string", "Optional browser, e.g. chrome, firefox, msedge")}, ["query"], category="web")
def search_in_browser(ctx, query: str, engine: str = "google", browser: str = ""):
    base = _ENGINES.get(engine, _ENGINES["google"])
    open_in_browser(base + urllib.parse.quote_plus(query) if engine != "maps" else base + urllib.parse.quote(query), browser)
    return f"OK: opened {engine} search for '{query}'"


@tool("Open a URL in the browser, or an app link (discord://, spotify:, ms-settings:..., mailto:).",
      {"url": P("string", "URL; a bare domain like 'youtube.com' gets https://"),
       "browser": P("string", "Optional browser, e.g. chrome")}, ["url"], category="web")
def open_url(ctx, url: str, browser: str = ""):
    url = url.strip()
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme in ("http", "https"):
        open_in_browser(url, browser)
    elif scheme in _APP_SCHEMES:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            webbrowser.open(url)
    elif not scheme or "." in url and "://" not in url and ":" not in url.split("/")[0]:
        open_in_browser("https://" + url, browser)
    else:
        return f"ERROR: I won't open '{scheme}:' links."
    return f"OK: opened {url}"


@tool("Search the web and return the top results (title, link, snippet) so you can answer questions with fresh info.",
      {"query": P("string", "Search query"), "max_results": P("integer", "Default 5")}, ["query"], category="web")
def web_search(ctx, query: str, max_results: int = 5):
    from bs4 import BeautifulSoup
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=_UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    soup, out = BeautifulSoup(r.text, "html.parser"), []
    for res in soup.select(".result")[: int(max_results) * 2]:
        a = res.select_one(".result__a")
        if not a:
            continue
        href = a.get("href", "")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        link = q["uddg"][0] if "uddg" in q else href
        sn = res.select_one(".result__snippet")
        out.append(f"{a.get_text(' ', strip=True)}\n{link}\n{sn.get_text(' ', strip=True) if sn else ''}")
        if len(out) >= int(max_results):
            break
    return "\n\n".join(out) or "No results (the search page may have changed or blocked the request)."


@tool("Download a web page and return its readable text.",
      {"url": P("string", "Page URL"), "max_chars": P("integer", "Default 4000")}, ["url"], category="web")
def read_webpage(ctx, url: str, max_chars: int = 4000):
    from bs4 import BeautifulSoup
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    r = httpx.get(url, headers=_UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        t.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text[: int(max_chars)] or "The page had no readable text."
