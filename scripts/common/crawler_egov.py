"""
ECHO OS Barebone: e-Gov API Crawler

Fetches law data from Japan's e-Gov API (https://laws.e-gov.go.jp).
This is a generic crawler - provide your own law IDs via configuration.

Usage:
    from scripts.common.crawler_egov import EgovApiCrawler

    crawler = EgovApiCrawler()
    result = crawler.fetch_law("322AC0000000049")  # 労働基準法

    # Or fetch multiple laws
    results = crawler.fetch_all_laws(["322AC0000000049", "349AC0000000116"])
"""

import logging
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger("EgovApiCrawler")


# =============================================================================
# Configuration (override via environment or parameters)
# =============================================================================

import os

# Maximum number of laws to fetch (safety limit)
MAX_FETCH_COUNT = int(os.getenv("EGOV_MAX_FETCH_COUNT", "500"))

# Delay between API requests (seconds)
REQUEST_DELAY = float(os.getenv("EGOV_REQUEST_DELAY", "1.0"))

# e-Gov display URL template
ELAWS_DISPLAY_URL_TEMPLATE = "https://elaws.e-gov.go.jp/document?lawid={law_id}"

# Enable URL health check
URL_HEALTH_CHECK_ENABLED = os.getenv("EGOV_URL_HEALTH_CHECK", "false").lower() == "true"
URL_HEALTH_CHECK_TIMEOUT = int(os.getenv("EGOV_URL_HEALTH_CHECK_TIMEOUT", "5"))


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EgovApiResult:
    """Result of fetching a law from e-Gov API."""
    law_id: str
    law_name: str
    law_num: str
    source_url: str
    articles: List[Dict] = field(default_factory=list)
    raw_xml: Optional[str] = None
    updated_at: str = ""
    content_hash: str = ""
    success: bool = True
    error: Optional[str] = None
    # Metadata
    layer: str = "law"                    # "law" or "order"
    parent_law_id: Optional[str] = None   # For orders, the parent law ID
    display_url: str = ""                 # Browser-viewable URL
    url_status: str = "unknown"           # "valid" or "broken"


# =============================================================================
# Crawler
# =============================================================================

class EgovApiCrawler:
    """
    Crawler for Japan's e-Gov Law API.
    Fetches law data in XML format from the official API.

    Example:
        crawler = EgovApiCrawler()
        result = crawler.fetch_law("322AC0000000049")
        for article in result.articles:
            print(f"{article['article_number']}: {article['text'][:100]}...")
    """

    API_BASE_URL = "https://laws.e-gov.go.jp/api/1/lawdata"

    def __init__(
        self,
        max_fetch_count: int = MAX_FETCH_COUNT,
        request_delay: float = REQUEST_DELAY,
    ):
        """
        Initialize the crawler.

        Args:
            max_fetch_count: Maximum number of laws to fetch (safety limit)
            request_delay: Delay between API requests in seconds
        """
        self.max_fetch_count = max_fetch_count
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "EchoOS-RAG/1.0 (Government Law API Client)",
            "Accept": "application/xml",
        })
        self.fetch_count = 0

    def _check_fetch_limit(self) -> bool:
        """Check if we've reached the fetch limit."""
        if self.fetch_count >= self.max_fetch_count:
            logger.warning(
                f"e-Gov API fetch limit reached: "
                f"{self.fetch_count}/{self.max_fetch_count}"
            )
            return False
        return True

    def _check_url_health(self, law_id: str) -> Tuple[str, str]:
        """
        Check if the display URL is accessible.

        Args:
            law_id: Law ID

        Returns:
            (display_url, url_status) - url_status is "valid" or "broken"
        """
        display_url = ELAWS_DISPLAY_URL_TEMPLATE.format(law_id=law_id)

        if not URL_HEALTH_CHECK_ENABLED:
            return display_url, "unknown"

        try:
            response = self.session.head(
                display_url,
                timeout=URL_HEALTH_CHECK_TIMEOUT,
                allow_redirects=True
            )
            url_status = "valid" if response.status_code == 200 else "broken"
            logger.debug(f"URL health check: {law_id} -> {url_status}")
            return display_url, url_status
        except Exception as e:
            logger.warning(f"URL health check failed: {law_id} -> {e}")
            return display_url, "broken"

    def _make_api_request(
        self,
        law_id: str,
        max_retries: int = 3
    ) -> Optional[str]:
        """
        Make API request with retry logic.

        Args:
            law_id: Law ID (e.g., "322AC0000000049")
            max_retries: Maximum number of retries

        Returns:
            XML response string or None if failed
        """
        url = f"{self.API_BASE_URL}/{law_id}"

        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching e-Gov API: law_id={law_id} (attempt {attempt + 1})")

                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    logger.info(f"API success: law_id={law_id}")
                    return response.text

                elif response.status_code == 404:
                    logger.warning(f"Law not found: law_id={law_id} (404)")
                    return None

                elif response.status_code == 429:
                    # Rate limited
                    wait_time = 60 * (attempt + 1)
                    logger.warning(f"Rate limited (429), waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                elif response.status_code >= 500:
                    # Server error
                    wait_time = 10 * (attempt + 1)
                    logger.warning(f"Server error ({response.status_code}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                else:
                    logger.error(f"Unexpected status: {response.status_code}")
                    return None

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}: law_id={law_id}")
                time.sleep(5 * (attempt + 1))

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: law_id={law_id} error={e}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))

            except Exception as e:
                logger.error(f"Unexpected error: law_id={law_id} error={e}")
                return None

        logger.error(f"All retries exhausted for law_id={law_id}")
        return None

    def _extract_articles(self, xml_text: str) -> List[Dict]:
        """
        Extract articles from e-Gov API XML response.

        Only extracts from MainProvision (本則).
        SupplProvision (附則/整備法令) articles are excluded.

        Args:
            xml_text: Raw XML response

        Returns:
            List of article dicts
        """
        articles = []

        try:
            root = ET.fromstring(xml_text)

            # Only extract from MainProvision (本則)
            article_elements = root.findall(".//{*}MainProvision//{*}Article")

            # Fallback: try without namespace
            if not article_elements:
                article_elements = root.findall(".//MainProvision//Article")

            logger.info(f"Found {len(article_elements)} articles in MainProvision")

            for article_elem in article_elements:
                article_num = article_elem.get("Num", "")

                # Get caption
                caption_elem = article_elem.find("./{*}ArticleCaption")
                caption = self._extract_text_from_xml(caption_elem) if caption_elem is not None else ""

                # Get title
                title_elem = article_elem.find("./{*}ArticleTitle")
                title = self._extract_text_from_xml(title_elem) if title_elem is not None else ""

                # Get paragraphs
                text_parts = []
                for para_elem in article_elem.findall("./{*}Paragraph"):
                    para_text = self._extract_text_from_xml(para_elem)
                    if para_text:
                        text_parts.append(para_text)

                full_text = "\n".join(text_parts) if text_parts else ""

                if full_text:
                    articles.append({
                        "article_number": article_num or f"Article_{len(articles) + 1}",
                        "caption": caption,
                        "title": title,
                        "text": f"{caption}\n{title}\n{full_text}".strip(),
                        "section_type": "law_article",
                    })

            logger.info(f"Extracted {len(articles)} articles")

        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
        except Exception as e:
            logger.error(f"Failed to extract articles: {e}")

        return articles

    def _extract_text_from_xml(self, element: ET.Element) -> str:
        """Recursively extract all text from XML element."""
        if element is None:
            return ""

        text_parts = []

        if element.text:
            text_parts.append(element.text.strip())

        for child in element:
            child_text = self._extract_text_from_xml(child)
            if child_text:
                text_parts.append(child_text)
            if child.tail:
                text_parts.append(child.tail.strip())

        return " ".join(filter(None, text_parts))

    def fetch_law(
        self,
        law_id: str,
        layer: str = "law",
        parent_law_id: Optional[str] = None
    ) -> EgovApiResult:
        """
        Fetch a single law from e-Gov API.

        Args:
            law_id: Law ID (e.g., "322AC0000000049")
            layer: "law" for laws, "order" for ministerial orders
            parent_law_id: For orders, the parent law ID

        Returns:
            EgovApiResult with articles and metadata
        """
        if not self._check_fetch_limit():
            return EgovApiResult(
                law_id=law_id,
                law_name="",
                law_num="",
                source_url="",
                success=False,
                error="Fetch limit reached"
            )

        xml_text = self._make_api_request(law_id)

        if not xml_text:
            return EgovApiResult(
                law_id=law_id,
                law_name="",
                law_num="",
                source_url=f"{self.API_BASE_URL}/{law_id}",
                success=False,
                error="API request failed"
            )

        self.fetch_count += 1

        # URL health check
        display_url, url_status = self._check_url_health(law_id)

        # Extract metadata
        try:
            root = ET.fromstring(xml_text)

            law_title_elem = root.find(".//{*}LawTitle")
            law_name = law_title_elem.text if law_title_elem is not None else law_id

            law_num_elem = root.find(".//{*}LawNum")
            law_num = law_num_elem.text if law_num_elem is not None else law_id

            updated_at = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            law_name = law_id
            law_num = law_id
            updated_at = datetime.now(timezone.utc).isoformat()

        # Extract articles
        articles = self._extract_articles(xml_text)

        # Generate content hash
        content_str = f"{law_id}_{law_name}_{'_'.join(a['text'][:50] for a in articles[:5])}"
        content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

        return EgovApiResult(
            law_id=law_id,
            law_name=law_name,
            law_num=law_num,
            source_url=f"{self.API_BASE_URL}/{law_id}",
            articles=articles,
            raw_xml=xml_text[:500] if xml_text else None,
            updated_at=updated_at,
            content_hash=content_hash,
            success=True,
            error=None,
            layer=layer,
            parent_law_id=parent_law_id,
            display_url=display_url,
            url_status=url_status,
        )

    def fetch_all_laws(self, law_ids: List[str]) -> List[EgovApiResult]:
        """
        Fetch multiple laws from e-Gov API.

        Args:
            law_ids: List of law IDs

        Returns:
            List of EgovApiResult
        """
        results = []

        logger.info(f"Fetching {len(law_ids)} laws from e-Gov API")

        for i, law_id in enumerate(law_ids):
            logger.info(f"[{i+1}/{len(law_ids)}] Fetching: {law_id}")
            result = self.fetch_law(law_id)
            results.append(result)

            # Polite delay
            if i < len(law_ids) - 1:
                time.sleep(self.request_delay)

        success_count = sum(1 for r in results if r.success)
        logger.info(f"Fetch complete: {success_count}/{len(results)} success")

        return results


# =============================================================================
# Utility Functions
# =============================================================================

def convert_to_chunks(api_results: List[EgovApiResult]) -> List[Dict]:
    """
    Convert EgovApiResult to chunk format for indexing.

    Args:
        api_results: List of EgovApiResult

    Returns:
        List of chunk dicts ready for indexing
    """
    chunks = []

    for result in api_results:
        if not result.success or not result.articles:
            continue

        for article in result.articles:
            chunks.append({
                "content": article["text"],
                "source": result.display_url or result.source_url,
                "metadata": {
                    "law_id": result.law_id,
                    "law_name": result.law_name,
                    "law_num": result.law_num,
                    "article_number": article["article_number"],
                    "section_type": article["section_type"],
                    "layer": result.layer,
                    "parent_law_id": result.parent_law_id,
                    "updated_at": result.updated_at,
                    "content_hash": result.content_hash,
                }
            })

    logger.info(f"Converted {len(api_results)} results to {len(chunks)} chunks")
    return chunks


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Fetch a single law
    crawler = EgovApiCrawler()

    # 労働基準法 (Labor Standards Act)
    result = crawler.fetch_law("322AC0000000049")

    if result.success:
        print(f"Law: {result.law_name}")
        print(f"Articles: {len(result.articles)}")
        for article in result.articles[:3]:
            print(f"  - {article['article_number']}: {article['text'][:100]}...")
    else:
        print(f"Failed: {result.error}")
