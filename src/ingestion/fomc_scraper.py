"""Download Federal Reserve FOMC statements and minutes from HTML pages.

The scraper is intentionally boring: it discovers official federalreserve.gov
links, caches every downloaded HTML page, writes extracted text next to it, and
skips cached files on later runs.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[2]
RAW_FOMC = ROOT / "data" / "raw" / "fomc"
CACHE_DIR = ROOT / "data" / "cache" / "fomc"

FED_BASE = "https://www.federalreserve.gov"
CURRENT_CALENDAR_URL = f"{FED_BASE}/monetarypolicy/fomccalendars.htm"
HISTORICAL_CALENDAR_URL = f"{FED_BASE}/monetarypolicy/fomchistorical{{year}}.htm"
USER_AGENT = (
    "TraceYield/1.0 FOMC research scraper "
    "(contact: local research pipeline; cache-first)"
)

_STATEMENT_RE = re.compile(r"/newsevents/pressreleases/monetary(\d{8})a\.htm$")
_MINUTES_RE = re.compile(r"/monetarypolicy/fomcminutes(\d{8})\.htm$")
_KIND_ORDER = {"statement": 0, "minutes": 1}


@dataclass(frozen=True)
class FomcLink:
    kind: str
    doc_date: date
    url: str


def classify_url(url: str) -> FomcLink | None:
    """Return FOMC link metadata for official statement/minutes URLs."""
    parsed = urlparse(url)
    path = parsed.path
    m = _STATEMENT_RE.search(path)
    kind = "statement"
    if not m:
        m = _MINUTES_RE.search(path)
        kind = "minutes"
    if not m:
        return None
    raw = m.group(1)
    return FomcLink(
        kind=kind,
        doc_date=date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])),
        url=url,
    )


def _normalize_text(value: str) -> str:
    value = unescape(value).replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _strip_boilerplate(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        line = _normalize_text(line)
        if not line:
            continue
        low = line.lower()
        if low in {"share", "email", "print"}:
            continue
        if low.startswith(("for media inquiries", "media contacts")):
            continue
        if low.startswith("implementation note issued"):
            continue
        if low.startswith(("last update:", "accessibility", "stay connected")):
            continue
        cleaned.append(line)
    return cleaned


def _extract_with_bs4(html: str) -> str | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()

    root = (
        soup.find(id="article")
        or soup.find("article")
        or soup.find("main")
        or soup.find(id="content")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"\barticle\b|\bcontent\b"))
        or soup.body
        or soup
    )
    lines = [
        node.get_text(" ", strip=True)
        for node in root.find_all(["h1", "h2", "h3", "p", "li"])
    ]
    if not lines:
        lines = [root.get_text("\n", strip=True)]
    return "\n\n".join(_strip_boilerplate(lines))


def _extract_links_with_bs4(html: str) -> list[str] | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True)]


class _ScopedTextParser(HTMLParser):
    def __init__(self, *, element_id: str | None = None, tag_name: str | None = None):
        super().__init__(convert_charrefs=True)
        self.element_id = element_id
        self.tag_name = tag_name
        self.active = False
        self.depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self.active:
            self.depth += 1
            if tag in {"p", "h1", "h2", "h3", "li", "div"}:
                self.chunks.append("\n")
            return

        if self.element_id and attrs_dict.get("id") == self.element_id:
            self.active = True
            self.depth = 1
        elif self.tag_name and tag == self.tag_name:
            self.active = True
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if not self.active:
            return
        if tag in {"p", "h1", "h2", "h3", "li", "div"}:
            self.chunks.append("\n")
        self.depth -= 1
        if self.depth <= 0:
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.chunks.append(data)

    def text(self) -> str:
        return "\n".join(_strip_boilerplate("".join(self.chunks).splitlines()))


def _scoped_text(
    html: str, *, element_id: str | None = None, tag_name: str | None = None
) -> str:
    parser = _ScopedTextParser(element_id=element_id, tag_name=tag_name)
    parser.feed(html)
    return parser.text()


def _fallback_text_extract(html: str) -> str:
    body = html
    for tag in ("nav", "header", "footer", "script", "style", "form"):
        body = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            "",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )

    for kwargs in (
        {"element_id": "article"},
        {"tag_name": "article"},
        {"tag_name": "main"},
        {"element_id": "content"},
    ):
        scoped = _scoped_text(body, **kwargs)
        if scoped:
            return scoped

    body = re.sub(r"</(?:p|h1|h2|h3|li|div)>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    return "\n\n".join(_strip_boilerplate(body.splitlines()))


def extract_release_text(html: str) -> str:
    """Extract readable policy text from a Fed statement/minutes HTML page."""
    return _normalize_text(_extract_with_bs4(html) or _fallback_text_extract(html))


def discover_doc_links_from_html(html: str, base_url: str) -> list[FomcLink]:
    """Find official statement and minutes links in a Fed calendar page."""
    hrefs = _extract_links_with_bs4(html)
    if hrefs is None:
        hrefs = re.findall(r"<a\b[^>]+href=[\"']([^\"']+)[\"']", html, re.I)

    found: dict[tuple[str, date], FomcLink] = {}
    for href in hrefs:
        url = urljoin(base_url, href)
        link = classify_url(url)
        if link:
            found[(link.kind, link.doc_date)] = link

    return sorted(
        found.values(),
        key=lambda link: (link.doc_date, _KIND_ORDER.get(link.kind, 99), link.url),
    )


def calendar_urls(start_year: int = 2010, end_year: int | None = None) -> list[str]:
    """Return Fed calendar URLs needed to discover docs from start_year onward."""
    end_year = end_year or date.today().year
    current_page_start = max(start_year, end_year - 5)
    urls = [CURRENT_CALENDAR_URL]
    for year in range(start_year, current_page_start):
        urls.append(HISTORICAL_CALENDAR_URL.format(year=year))
    return urls


def _session():
    try:
        import requests
    except ImportError:
        return None

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _cache_path_for_url(url: str, suffix: str = ".html") -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", urlparse(url).path).strip("_")
    return CACHE_DIR / f"{slug}{suffix}"


def fetch_url(url: str, *, session=None, force: bool = False) -> str:
    """Fetch URL with a cache-first policy."""
    cache_path = _cache_path_for_url(url)
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8")

    s = session if session is not None else _session()
    if s is not None:
        response = s.get(url, timeout=30)
        response.raise_for_status()
        text = response.text
    else:
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=30) as response:  # noqa: S310 - official Fed URL
            charset = response.headers.get_content_charset() or "utf-8"
            text = response.read().decode(charset, errors="replace")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    return text


def _paths_for_link(link: FomcLink, raw_root: Path = RAW_FOMC) -> tuple[Path, Path]:
    stem = link.doc_date.isoformat()
    folder = raw_root / link.kind
    return folder / f"{stem}.html", folder / f"{stem}.txt"


def _write_doc(link: FomcLink, html: str, raw_root: Path = RAW_FOMC) -> Path:
    html_path, text_path = _paths_for_link(link, raw_root)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(extract_release_text(html), encoding="utf-8")
    return text_path


def _to_fomc_doc(link: FomcLink, text_path: Path):
    from src.nlp.fomc_loader import FomcDoc

    return FomcDoc(
        kind=link.kind,
        doc_date=link.doc_date,
        path=text_path,
        text=text_path.read_text(encoding="utf-8"),
        source="federalreserve.gov",
    )


def scrape(
    start_year: int = 2010,
    *,
    force: bool = False,
    sleep_seconds: float = 0.5,
    limit: int | None = None,
) -> list:
    """Discover, download, cache, and load FOMC statement/minutes HTML docs."""
    session = _session()
    links: dict[tuple[str, date], FomcLink] = {}
    for url in calendar_urls(start_year=start_year):
        html = fetch_url(url, session=session, force=force)
        for link in discover_doc_links_from_html(html, base_url=url):
            if link.doc_date.year >= start_year:
                links[(link.kind, link.doc_date)] = link

    docs = []
    for link in sorted(links.values(), key=lambda x: (x.doc_date, _KIND_ORDER[x.kind])):
        if limit is not None and len(docs) >= limit:
            break
        html_path, text_path = _paths_for_link(link)
        if not text_path.exists() or force:
            html = fetch_url(link.url, session=session, force=force)
            text_path = _write_doc(link, html)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        elif not html_path.exists():
            html = fetch_url(link.url, session=session, force=False)
            html_path.write_text(html, encoding="utf-8")
        docs.append(_to_fomc_doc(link, text_path))
    return docs


def scrape_url(url: str, *, force: bool = False) -> object:
    """Download one known statement/minutes URL, useful for manual review."""
    link = classify_url(url)
    if not link:
        raise ValueError(f"Unsupported FOMC statement/minutes URL: {url}")
    html = fetch_url(link.url, force=force)
    text_path = _write_doc(link, html)
    return _to_fomc_doc(link, text_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--url", help="Download one statement/minutes URL")
    parser.add_argument("--force", action="store_true", help="Re-download cached files")
    parser.add_argument(
        "--sleep", type=float, default=0.5, help="Seconds between doc downloads"
    )
    parser.add_argument("--limit", type=int, help="Limit docs downloaded, for testing")
    args = parser.parse_args(argv)

    if args.url:
        doc = scrape_url(args.url, force=args.force)
        print(f"{doc.kind} {doc.doc_date} {len(doc.text)} chars -> {doc.path}")
        return

    docs = scrape(
        start_year=args.start_year,
        force=args.force,
        sleep_seconds=args.sleep,
        limit=args.limit,
    )
    counts = {"statement": 0, "minutes": 0}
    for doc in docs:
        counts[doc.kind] = counts.get(doc.kind, 0) + 1
    print(
        f"Downloaded/loaded {len(docs)} docs: "
        f"{counts.get('statement', 0)} statements, {counts.get('minutes', 0)} minutes"
    )


if __name__ == "__main__":
    main()
