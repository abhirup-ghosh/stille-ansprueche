"""Phase 1b: best-effort plain-language enrichment from official portals.

Sources, in priority order:
1. sozialplattform.de (federal social services portal) — discovered via /sitemap.xml
   (5138 URLs; filtered down to benefit-name-token candidates before fetching anything).
2. familienportal.de (federal family portal, BMFSFJ) — sitemap.xml itself 404s; robots.txt
   points at a sitemap index whose single child sitemap (gzipped) lists 127 URLs.

Politeness: custom User-Agent, robots.txt respected via urllib.robotparser (including its
declared Crawl-delay — sozialplattform.de asks for 10s), every HTTP response cached to
data/raw_html/ so re-runs never re-fetch, no deep crawling (sitemap/index discovery only).
"""
import gzip
import hashlib
import json
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from src import config

USER_AGENT = "stille-ansprueche-research-bot/0.1 (educational project)"
MIN_DELAY_S = 1.0
MATCH_SCORE_THRESHOLD = 85
TOKEN_MIN_LEN = 5

RAW_HTML_DIR = config.DATA_DIR / "raw_html"
IFO_PARSED_PATH = config.DATA_DIR / "ifo" / "benefits_parsed.jsonl"
EXTRACTED_PATH = RAW_HTML_DIR / "extracted.jsonl"
ENRICHMENT_PATH = config.DATA_DIR / "ifo" / "enrichment.jsonl"
ATTRIBUTION_PATH = config.DATA_DIR / "ATTRIBUTION.md"

SITEMAP_XML_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

TRANSLIT = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})


def tokenize(text: str) -> set[str]:
    s = text.translate(TRANSLIT).lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= TOKEN_MIN_LEN}


_last_fetch_at: dict[str, float] = {}
_robot_parsers: dict[str, urllib.robotparser.RobotFileParser] = {}


def _domain(url: str) -> str:
    return urlparse(url).netloc


def _get_robot_parser(url: str) -> urllib.robotparser.RobotFileParser:
    domain = _domain(url)
    if domain not in _robot_parsers:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            rp.read()
        except Exception:  # noqa: BLE001
            pass
        _robot_parsers[domain] = rp
    return _robot_parsers[domain]


def _crawl_delay(url: str) -> float:
    rp = _get_robot_parser(url)
    delay = rp.crawl_delay(USER_AGENT)
    return max(MIN_DELAY_S, float(delay)) if delay else MIN_DELAY_S


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return RAW_HTML_DIR / f"{h}.html"


def fetch(url: str) -> str | None:
    """Fetch a URL respecting robots.txt and crawl-delay, caching every response to disk."""
    rp = _get_robot_parser(url)
    if not rp.can_fetch(USER_AGENT, url):
        print(f"[enrich_portals] robots.txt disallows {url}, skipping")
        return None

    cache_file = _cache_path(url)
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    domain = _domain(url)
    delay = _crawl_delay(url)
    last = _last_fetch_at.get(domain, 0.0)
    wait = delay - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        _last_fetch_at[domain] = time.monotonic()
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"[enrich_portals] fetch failed for {url}: {e}")
        return None

    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    return resp.text


def get_sozialplattform_urls() -> list[str]:
    xml = fetch("https://sozialplattform.de/sitemap.xml")
    if not xml:
        return []
    root = ET.fromstring(xml)
    return [el.text for el in root.findall(".//s:loc", SITEMAP_XML_NS) if el.text]


def get_familienportal_urls() -> list[str]:
    # sitemap.xml itself 404s on this site; robots.txt names the real sitemap index.
    robots = fetch("https://familienportal.de/robots.txt")
    if not robots:
        return []
    sitemap_index_url = None
    for line in robots.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_index_url = line.split(":", 1)[1].strip()
            break
    if not sitemap_index_url:
        return []

    index_xml = fetch(sitemap_index_url)
    if not index_xml:
        return []
    index_root = ET.fromstring(index_xml)
    child_sitemap_urls = [el.text for el in index_root.findall(".//s:loc", SITEMAP_XML_NS) if el.text]

    urls: list[str] = []
    for child_url in child_sitemap_urls:
        rp = _get_robot_parser(child_url)
        if not rp.can_fetch(USER_AGENT, child_url):
            continue
        cache_file = _cache_path(child_url)
        if cache_file.exists():
            raw_bytes = cache_file.read_bytes()
        else:
            domain = _domain(child_url)
            delay = _crawl_delay(child_url)
            last = _last_fetch_at.get(domain, 0.0)
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = requests.get(child_url, headers={"User-Agent": USER_AGENT}, timeout=20)
                _last_fetch_at[domain] = time.monotonic()
                resp.raise_for_status()
                raw_bytes = resp.content
            except Exception as e:  # noqa: BLE001
                print(f"[enrich_portals] fetch failed for {child_url}: {e}")
                continue
            RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(raw_bytes)

        if child_url.endswith(".gz"):
            raw_bytes = gzip.decompress(raw_bytes)
        child_root = ET.fromstring(raw_bytes)
        urls.extend(el.text for el in child_root.findall(".//s:loc", SITEMAP_XML_NS) if el.text)
    return urls


def filter_candidate_urls(urls: list[str], benefit_tokens: set[str]) -> list[str]:
    candidates = []
    for url in urls:
        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if tokenize(slug.replace("-", " ")) & benefit_tokens:
            candidates.append(url)
    return candidates


@dataclass
class ExtractedPage:
    url: str
    title: str
    text: str


def extract_page(url: str, html: str) -> ExtractedPage | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    title = (h1.get_text(strip=True) if h1 else None) or (title_tag.get_text(strip=True) if title_tag else "")

    content_el = soup.find("main") or soup.find("article") or soup.find("body")
    if content_el is None:
        return None
    text = re.sub(r"\s+", " ", content_el.get_text(" ", strip=True)).strip()
    if len(text) < 200:
        return None
    return ExtractedPage(url=url, title=title, text=text)


def match_pages_to_benefits(pages: list[ExtractedPage], benefits: list[dict]) -> list[dict]:
    best_per_benefit: dict[str, tuple[int, ExtractedPage]] = {}
    for benefit in benefits:
        best_score = -1
        best_page = None
        for page in pages:
            if not page.title:
                continue
            score = fuzz.token_set_ratio(benefit["name"], page.title)
            if score > best_score:
                best_score = score
                best_page = page
        if best_page is not None and best_score >= MATCH_SCORE_THRESHOLD:
            best_per_benefit[benefit["id"]] = (best_score, best_page)

    return [
        {"benefit_id": benefit_id, "url": page.url, "title": page.title, "text": page.text}
        for benefit_id, (score, page) in best_per_benefit.items()
    ]


def append_attribution(enriched_count: int, total_benefits: int) -> None:
    existing = ATTRIBUTION_PATH.read_text(encoding="utf-8") if ATTRIBUTION_PATH.exists() else ""
    marker = "## Portal enrichment (Phase 1b)"
    section = f"""{marker}

- **sozialplattform.de** (federal social services portal, operated on behalf of the BMAS):
  plain-language benefit description pages, discovered via `/sitemap.xml` and filtered to
  benefit-name-token candidates. Fetched with a custom User-Agent and crawl-delay 10s per its
  robots.txt.
- **familienportal.de** (federal family portal, BMFSFJ): plain-language benefit description
  pages, discovered via the sitemap index referenced in its robots.txt.
- Both accessed under `robots.txt` permission, cached under `data/raw_html/` (git-ignored),
  content used only as short excerpts appended to the corresponding benefit's corpus text.
- **Result:** {enriched_count} / {total_benefits} benefits enriched with plain-language text.
"""
    if marker in existing:
        pre = existing[: existing.index(marker)]
        existing = pre
    ATTRIBUTION_PATH.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")


def main():
    with open(IFO_PARSED_PATH, encoding="utf-8") as f:
        benefits = [json.loads(line) for line in f]

    benefit_tokens: set[str] = set()
    for b in benefits:
        benefit_tokens |= tokenize(b["name"])

    print("[enrich_portals] Discovering candidate URLs from sitemaps...")
    sp_urls = get_sozialplattform_urls()
    fp_urls = get_familienportal_urls()
    print(f"[enrich_portals] sozialplattform.de: {len(sp_urls)} sitemap URLs")
    print(f"[enrich_portals] familienportal.de: {len(fp_urls)} sitemap URLs")

    candidates = filter_candidate_urls(sp_urls, benefit_tokens) + filter_candidate_urls(fp_urls, benefit_tokens)
    print(f"[enrich_portals] {len(candidates)} candidate URLs after token filtering")

    pages: list[ExtractedPage] = []
    for i, url in enumerate(candidates, 1):
        html = fetch(url)
        if not html:
            continue
        page = extract_page(url, html)
        if page:
            pages.append(page)
        if i % 20 == 0:
            print(f"[enrich_portals] fetched {i}/{len(candidates)}")

    print(f"[enrich_portals] Extracted {len(pages)} usable pages")

    EXTRACTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXTRACTED_PATH, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps({"url": page.url, "title": page.title, "text": page.text}, ensure_ascii=False) + "\n")

    enrichment_rows = match_pages_to_benefits(pages, benefits)

    ENRICHMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENRICHMENT_PATH, "w", encoding="utf-8") as f:
        for row in enrichment_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if pages:
        append_attribution(len(enrichment_rows), len(benefits))

    print(f"\n[enrich_portals] Enriched {len(enrichment_rows)} / {len(benefits)} benefits")
    print(f"[enrich_portals] Wrote {EXTRACTED_PATH} and {ENRICHMENT_PATH}")


if __name__ == "__main__":
    main()
