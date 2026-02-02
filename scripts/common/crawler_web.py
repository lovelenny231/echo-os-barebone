"""
ECHO OS Barebone: Generic Web Crawler

A configurable web crawler for collecting data from websites.
Supports HTML and PDF content with encoding validation.

Usage:
    from scripts.common.crawler_web import WebCrawler, CrawlConfig

    # Configure crawler
    config = CrawlConfig(
        seed_urls=["https://example.com/docs"],
        allowed_path_prefixes=["/docs"],
        max_depth=2,
        max_urls=100,
    )

    # Crawl
    crawler = WebCrawler()
    results = crawler.crawl(config)

    for result in results:
        if result.success:
            print(f"{result.url}: {len(result.text)} chars")
"""

import logging
import hashlib
import time
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("WebCrawler")


# =============================================================================
# Configuration
# =============================================================================

import os

# Default limits
DEFAULT_MAX_URLS = int(os.getenv("CRAWLER_MAX_URLS", "300"))
DEFAULT_MAX_DEPTH = int(os.getenv("CRAWLER_MAX_DEPTH", "2"))
DEFAULT_MAX_PDF_MB = float(os.getenv("CRAWLER_MAX_PDF_MB", "10"))
DEFAULT_MAX_TEXT_CHARS = int(os.getenv("CRAWLER_MAX_TEXT_CHARS", "250000"))
DEFAULT_REQUEST_DELAY = float(os.getenv("CRAWLER_REQUEST_DELAY", "1.0"))


@dataclass
class CrawlConfig:
    """Configuration for a crawl job."""
    seed_urls: List[str]                           # Starting URLs
    allowed_path_prefixes: List[str] = None        # Allowed path prefixes (None = allow all)
    allowed_domains: List[str] = None              # Allowed domains (None = same domain only)
    max_urls: int = DEFAULT_MAX_URLS               # Max URLs to crawl
    max_depth: int = DEFAULT_MAX_DEPTH             # Max crawl depth
    max_pdf_mb: float = DEFAULT_MAX_PDF_MB         # Max PDF size in MB
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS   # Max text chars per page
    request_delay: float = DEFAULT_REQUEST_DELAY   # Delay between requests
    user_agent: str = "EchoOS-Crawler/1.0"         # User-Agent header
    follow_links: bool = True                      # Whether to follow links


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CrawlResult:
    """Result of crawling a single URL."""
    url: str
    domain: str
    content_type: str  # 'html' or 'pdf'
    text: Optional[str] = None
    title: str = ""
    encoding: str = ""
    content_hash: str = ""
    crawled_at: str = ""
    success: bool = False
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: str = ""
    links: List[str] = field(default_factory=list)
    depth: int = 0


@dataclass
class CrawlStats:
    """Statistics for a crawl run."""
    urls_attempted: int = 0
    urls_success: int = 0
    urls_failed: int = 0
    urls_skipped: int = 0


# =============================================================================
# Encoding Utilities
# =============================================================================

# Common garbage characters that indicate encoding issues
GARBAGE_CHARS = re.compile(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]')
MAX_GARBAGE_RATIO = 0.01


def is_encoding_ok(text: str) -> bool:
    """Check if text has acceptable encoding quality."""
    if not text:
        return False

    garbage_count = len(GARBAGE_CHARS.findall(text))
    ratio = garbage_count / len(text) if text else 1.0

    return ratio < MAX_GARBAGE_RATIO


def normalize_text(raw_bytes: bytes, url: str = "") -> Tuple[Optional[str], str, bool]:
    """
    Normalize bytes to text with encoding detection.

    Returns:
        (text, encoding, success)
    """
    encodings = ["utf-8", "cp932", "shift_jis", "euc-jp", "iso-2022-jp", "latin-1"]

    for encoding in encodings:
        try:
            text = raw_bytes.decode(encoding)
            if is_encoding_ok(text):
                return text, encoding, True
        except (UnicodeDecodeError, LookupError):
            continue

    # Last resort: decode with errors='replace'
    text = raw_bytes.decode("utf-8", errors="replace")
    return text, "utf-8-fallback", False


# =============================================================================
# Web Crawler
# =============================================================================

class WebCrawler:
    """
    Generic web crawler with BFS traversal.

    Features:
    - Respects rate limits and max URL counts
    - Handles HTML and PDF content
    - Validates text encoding
    - Follows links within allowed domains/paths
    """

    def __init__(self):
        self.session = requests.Session()
        self.visited_urls: Set[str] = set()
        self.stats = CrawlStats()

    def _setup_session(self, config: CrawlConfig):
        """Setup session with config."""
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/pdf",
            "Accept-Language": "en,ja;q=0.9",
        })

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc

    def _is_url_allowed(
        self,
        url: str,
        config: CrawlConfig,
        seed_domain: str
    ) -> Tuple[bool, str]:
        """Check if URL is allowed by config."""
        parsed = urlparse(url)
        domain = parsed.netloc
        path = parsed.path

        # Check domain
        if config.allowed_domains:
            if domain not in config.allowed_domains:
                return False, f"domain_not_allowed: {domain}"
        else:
            # Default: same domain only
            if domain != seed_domain:
                return False, f"different_domain: {domain}"

        # Check path
        if config.allowed_path_prefixes:
            allowed = any(path.startswith(prefix) for prefix in config.allowed_path_prefixes)
            if not allowed:
                return False, f"path_not_allowed: {path}"

        return True, ""

    def _extract_pdf_text(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF."""
        try:
            import pdfplumber
            import io

            text_parts = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            return "\n\n".join(text_parts) if text_parts else None

        except ImportError:
            logger.warning("pdfplumber not installed, skipping PDF")
            return None
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return None

    def _extract_html(
        self,
        html_bytes: bytes,
        base_url: str,
        config: CrawlConfig,
        seed_domain: str
    ) -> Tuple[Optional[str], str, List[str]]:
        """
        Extract text and links from HTML.

        Returns:
            (text, title, links)
        """
        text, encoding, success = normalize_text(html_bytes, base_url)

        if not text:
            return None, "", []

        try:
            soup = BeautifulSoup(text, "html.parser")

            # Extract title
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            # Remove non-content elements
            for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
                tag.decompose()

            # Extract main text
            main_text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            main_text = re.sub(r'\n\s*\n', '\n\n', main_text)
            main_text = main_text.strip()

            # Check length limit
            if len(main_text) > config.max_text_chars:
                logger.warning(f"Text too long: {len(main_text)} chars, truncating")
                main_text = main_text[:config.max_text_chars]

            # Extract links
            links = []
            if config.follow_links:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full_url = urljoin(base_url, href)

                    # Check if link is allowed
                    allowed, _ = self._is_url_allowed(full_url, config, seed_domain)
                    if allowed and full_url not in self.visited_urls:
                        links.append(full_url)

            return main_text, title, links

        except Exception as e:
            logger.error(f"HTML parsing failed: {e}")
            return None, "", []

    def crawl_url(
        self,
        url: str,
        config: CrawlConfig,
        seed_domain: str,
        depth: int = 0
    ) -> CrawlResult:
        """Crawl a single URL."""
        domain = self._get_domain(url)
        result = CrawlResult(
            url=url,
            domain=domain,
            content_type="unknown",
            crawled_at=datetime.now(timezone.utc).isoformat(),
            depth=depth,
        )

        # Check if already visited
        if url in self.visited_urls:
            result.skipped = True
            result.skip_reason = "already_visited"
            return result

        self.visited_urls.add(url)

        # Check URL limit
        if self.stats.urls_success >= config.max_urls:
            result.skipped = True
            result.skip_reason = "max_urls_reached"
            return result

        # Check depth
        if depth > config.max_depth:
            result.skipped = True
            result.skip_reason = f"depth_exceeded: {depth} > {config.max_depth}"
            return result

        # Check if URL is allowed
        allowed, reason = self._is_url_allowed(url, config, seed_domain)
        if not allowed:
            result.skipped = True
            result.skip_reason = reason
            self.stats.urls_skipped += 1
            return result

        self.stats.urls_attempted += 1

        try:
            logger.info(f"Fetching: {url} (depth={depth})")
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")

            if "application/pdf" in content_type or url.endswith(".pdf"):
                result.content_type = "pdf"

                # Check PDF size
                content_length = int(response.headers.get("Content-Length", 0))
                if content_length > config.max_pdf_mb * 1024 * 1024:
                    result.skipped = True
                    result.skip_reason = f"pdf_too_large: {content_length / 1024 / 1024:.1f}MB"
                    self.stats.urls_skipped += 1
                    return result

                pdf_bytes = response.content
                result.content_hash = hashlib.sha256(pdf_bytes).hexdigest()

                text = self._extract_pdf_text(pdf_bytes)
                if text:
                    result.text = text
                    result.encoding = "pdf"
                    result.success = True
                    self.stats.urls_success += 1
                else:
                    result.error = "PDF text extraction failed"
                    self.stats.urls_failed += 1

            else:
                result.content_type = "html"
                html_bytes = response.content
                result.content_hash = hashlib.sha256(html_bytes).hexdigest()

                text, title, links = self._extract_html(
                    html_bytes, url, config, seed_domain
                )

                if text and is_encoding_ok(text):
                    result.text = text
                    result.title = title
                    result.links = links
                    result.success = True
                    self.stats.urls_success += 1
                elif text:
                    result.text = text
                    result.title = title
                    result.error = "encoding_issues"
                    self.stats.urls_failed += 1
                else:
                    result.error = "no_text_extracted"
                    self.stats.urls_failed += 1

            # Polite delay
            time.sleep(config.request_delay)

        except requests.exceptions.RequestException as e:
            result.error = str(e)
            self.stats.urls_failed += 1
            logger.error(f"Request failed: {url} - {e}")

        except Exception as e:
            result.error = str(e)
            self.stats.urls_failed += 1
            logger.error(f"Unexpected error: {url} - {e}")

        return result

    def crawl(self, config: CrawlConfig) -> List[CrawlResult]:
        """
        Crawl URLs using BFS traversal.

        Args:
            config: CrawlConfig with seed URLs and settings

        Returns:
            List of CrawlResult objects
        """
        self._setup_session(config)
        self.visited_urls.clear()
        self.stats = CrawlStats()

        results = []
        seed_domain = self._get_domain(config.seed_urls[0]) if config.seed_urls else ""

        # BFS queue: (url, depth)
        queue = [(url, 0) for url in config.seed_urls]

        while queue and self.stats.urls_success < config.max_urls:
            url, depth = queue.pop(0)

            result = self.crawl_url(url, config, seed_domain, depth)
            results.append(result)

            # Add discovered links to queue
            if result.links and depth < config.max_depth:
                for link in result.links[:50]:  # Limit links per page
                    if link not in self.visited_urls:
                        queue.append((link, depth + 1))

        logger.info(
            f"Crawl complete: "
            f"attempted={self.stats.urls_attempted} "
            f"success={self.stats.urls_success} "
            f"failed={self.stats.urls_failed} "
            f"skipped={self.stats.urls_skipped}"
        )

        return results

    def get_stats(self) -> CrawlStats:
        """Get crawl statistics."""
        return self.stats


# =============================================================================
# Utility Functions
# =============================================================================

def convert_to_chunks(results: List[CrawlResult]) -> List[Dict]:
    """
    Convert CrawlResults to chunk format for indexing.

    Args:
        results: List of CrawlResult

    Returns:
        List of chunk dicts
    """
    chunks = []

    for result in results:
        if not result.success or not result.text:
            continue

        chunks.append({
            "content": result.text,
            "source": result.url,
            "metadata": {
                "title": result.title,
                "domain": result.domain,
                "content_type": result.content_type,
                "content_hash": result.content_hash,
                "crawled_at": result.crawled_at,
            }
        })

    logger.info(f"Converted {len(results)} results to {len(chunks)} chunks")
    return chunks


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Crawl a documentation site
    config = CrawlConfig(
        seed_urls=["https://docs.python.org/3/library/"],
        allowed_path_prefixes=["/3/library/"],
        max_urls=10,
        max_depth=1,
    )

    crawler = WebCrawler()
    results = crawler.crawl(config)

    print(f"\nCrawled {len(results)} pages:")
    for r in results:
        if r.success:
            print(f"  OK: {r.url} ({len(r.text)} chars)")
        elif r.skipped:
            print(f"  SKIP: {r.url} ({r.skip_reason})")
        else:
            print(f"  FAIL: {r.url} ({r.error})")
