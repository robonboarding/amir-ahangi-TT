"""Keyless grounding in rabobank.nl content.

Searches rabobank.nl through the DuckDuckGo Lite HTML endpoint (no API key), fetches
the top result pages, and extracts readable text so the language model can answer from
up-to-date Rabobank information and cite the source links.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("chatbot.backend.search")

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
ALLOWED_HOSTS = ("rabobank.nl", "rabobank.com")
# DuckDuckGo Lite serves real results to a browser UA; rabobank.nl's WAF blocks that
# same UA (403) but accepts a plain, self-identifying one, so we use one per endpoint.
SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RaboTT/1.0"}
SEARCH_TIMEOUT = 8
FETCH_TIMEOUT = 8
MAX_PAGE_CHARS = 1500
STRIP_TAGS = ("script", "style", "noscript", "header", "footer", "nav", "form", "svg")

# Fallback when DuckDuckGo throttles us: canonical rabobank.nl pages for common topics,
# matched by keyword. Pages are still fetched live, so answers stay up to date.
CURATED_PAGES = (
    (
        ("fraud", "fraude", "phishing", "scam", "spoofing", "oplichting", "melden"),
        (
            ("Fraude melden - Rabobank", "https://www.rabobank.nl/veiligbankieren/fraude-melden"),
            ("Phishing herkennen - Rabobank", "https://www.rabobank.nl/veiligbankieren/fraude-herkennen/phishing"),
        ),
    ),
    (
        ("contact", "phone", "call", "reach", "bellen", "klantenservice", "telefoon"),
        (("Contact - Rabobank", "https://www.rabobank.nl/particulieren/contact"),),
    ),
    (
        ("debit", "betaalpas", "block", "blokkeren", "deblokkeren", "replace", "lost", "stolen", "pas"),
        (("Betaalpas deblokkeren - Rabobank", "https://www.rabobank.nl/particulieren/service/betaalpas/betaalpas-deblokkeren"),),
    ),
    (
        ("credit", "creditcard"),
        (("Creditcard - Rabobank", "https://www.rabobank.nl/particulieren/creditcard"),),
    ),
    (
        ("mortgage", "hypotheek", "home loan", "house", "huis"),
        (("Hypotheek - Rabobank", "https://www.rabobank.nl/particulieren/hypotheek"),),
    ),
    (
        ("payment", "pay", "betalen", "transfer", "overboeken", "ideal"),
        (("Betalen - Rabobank", "https://www.rabobank.nl/particulieren/betalen"),),
    ),
    (
        ("online", "mobile", "app", "banking", "bankieren", "inloggen", "login"),
        (("Online en mobiel bankieren - Rabobank", "https://www.rabobank.nl/particulieren/betalen/online-mobiel-bankieren"),),
    ),
    (
        ("saving", "savings", "sparen", "spaar"),
        (("Sparen - Rabobank", "https://www.rabobank.nl/particulieren/sparen"),),
    ),
)


def _is_rabobank(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


@lru_cache(maxsize=128)
def search_rabobank(query: str, max_results: int = 4) -> Tuple[Tuple[str, str], ...]:
    """Return up to ``max_results`` (title, url) pairs from rabobank.nl for ``query``."""
    response = requests.post(
        DDG_LITE_URL,
        data={"q": f"site:rabobank.nl {query}"},
        headers=SEARCH_HEADERS,
        timeout=SEARCH_TIMEOUT,
    )
    if response.status_code != 200:
        # DuckDuckGo answers 202 with a challenge page when it rate-limits us; treat
        # anything but 200 as "no results" so the caller falls back to curated pages.
        logger.warning("DuckDuckGo search returned HTTP %s; using fallback", response.status_code)
        return ()
    soup = BeautifulSoup(response.text, "html.parser")

    hits: List[Tuple[str, str]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        match = re.search(r"uddg=([^&]+)", anchor["href"])
        url = urllib.parse.unquote(match.group(1)) if match else anchor["href"]
        if not url.startswith("http") or not _is_rabobank(url) or url in seen:
            continue
        seen.add(url)
        hits.append((anchor.get_text(strip=True) or url, url))
        if len(hits) >= max_results:
            break
    return tuple(hits)


@lru_cache(maxsize=128)
def fetch_page_text(url: str) -> str:
    """Fetch ``url`` and return collapsed, tag-free text from its main content."""
    response = requests.get(url, headers=FETCH_HEADERS, timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(list(STRIP_TAGS)):
        tag.decompose()
    main = soup.find("main") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(separator=" ", strip=True))
    return text[:MAX_PAGE_CHARS]


def _safe_fetch(url: str) -> str:
    try:
        return fetch_page_text(url)
    except Exception:  # noqa: BLE001 - one bad page must not break grounding
        logger.warning("Failed to fetch %s", url)
        return ""


def _curated_hits(query: str, max_results: int) -> Tuple[Tuple[str, str], ...]:
    lowered = query.lower()
    hits: List[Tuple[str, str]] = []
    seen = set()
    for keywords, pages in CURATED_PAGES:
        if any(keyword in lowered for keyword in keywords):
            for title, url in pages:
                if url not in seen:
                    seen.add(url)
                    hits.append((title, url))
    return tuple(hits[:max_results])


def build_grounding(query: str, max_sources: int = 3) -> Tuple[str, List[dict]]:
    """Search Rabobank for ``query`` and return (context_text, sources).

    Tries the keyless DuckDuckGo search first; if it is throttled or returns nothing,
    falls back to curated rabobank.nl pages matched by keyword. Either way the pages are
    fetched live and any network failure degrades to an empty context so the chat still
    answers.
    """
    try:
        hits = search_rabobank(query, max_results=max_sources + 2)
    except Exception:  # noqa: BLE001 - search must never break the chat
        logger.exception("Rabobank search failed")
        hits = ()

    if not hits:
        hits = _curated_hits(query, max_sources + 2)

    selected = list(hits)[:max_sources]
    if not selected:
        return "", []

    with ThreadPoolExecutor(max_workers=len(selected)) as pool:
        texts = list(pool.map(_safe_fetch, [url for _, url in selected]))

    blocks: List[str] = []
    sources: List[dict] = []
    for (title, url), text in zip(selected, texts):
        if not text:
            continue
        index = len(sources) + 1
        blocks.append(f"[{index}] {title}\nURL: {url}\n{text}")
        sources.append({"title": title, "url": url})

    return "\n\n".join(blocks), sources
