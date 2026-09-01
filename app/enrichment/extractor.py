"""HTML evidence parser and factual information extractor using BeautifulSoup."""

import re
from typing import Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Comment

from app.enrichment.schemas import DiscoveredLink, ExtractedPageFacts


class HtmlEvidenceExtractor:
    """Extracts factual evidence from raw HTML pages using bounded heuristics."""

    CAREER_KEYWORDS = ("career", "careers", "job", "jobs", "hiring", "join-us", "join_us", "openings", "work-with-us", "work_at")
    ABOUT_KEYWORDS = ("about", "about-us", "about_us", "company", "team", "story", "mission")
    PRODUCT_KEYWORDS = ("product", "products", "solution", "solutions", "pricing", "features", "platform")

    def __init__(
        self,
        max_headings: int = 15,
        max_text_length: int = 2500,
        max_discovered_links: int = 25,
    ) -> None:
        self.max_headings = max_headings
        self.max_text_length = max_text_length
        self.max_discovered_links = max_discovered_links

    def extract(self, html_text: str, base_url: str) -> ExtractedPageFacts:
        """Parse raw HTML and extract structured, bounded evidence facts."""
        if not html_text or not html_text.strip():
            return ExtractedPageFacts(
                url=base_url,
                raw_size_bytes=0,
                main_text_snippet="",
            )

        raw_size = len(html_text.encode("utf-8", errors="ignore"))

        try:
            soup = BeautifulSoup(html_text, "lxml")
        except Exception:
            soup = BeautifulSoup(html_text, "html.parser")

        # 1. Extract Meta properties before stripping tags
        page_title = self._extract_title(soup)
        meta_desc = self._extract_meta_description(soup)
        og_title = self._extract_meta_tag(soup, property_name="og:title")
        og_desc = self._extract_meta_tag(soup, property_name="og:description")

        # 2. Discover relevant links before stripping navigation
        discovered_links, careers_url = self._extract_links(soup, base_url)

        # 3. Extract Headings (H1, H2, H3)
        headings = self._extract_headings(soup)

        # 4. Clean noisy elements to isolate main content
        self._strip_noise(soup)

        # 5. Extract Main Text snippet
        main_text = self._extract_main_text(soup)

        return ExtractedPageFacts(
            url=base_url,
            page_title=page_title,
            meta_description=meta_desc,
            og_title=og_title,
            og_description=og_desc,
            headings=headings,
            main_text_snippet=main_text,
            discovered_links=discovered_links,
            careers_url=careers_url,
            raw_size_bytes=raw_size,
        )

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract title tag or OpenGraph title."""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            if title:
                return title[:200]
        og_title = self._extract_meta_tag(soup, property_name="og:title")
        if og_title:
            return og_title[:200]
        return None

    def _extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract meta description or OpenGraph description."""
        desc = self._extract_meta_tag(soup, name="description")
        if desc:
            return desc[:500]
        og_desc = self._extract_meta_tag(soup, property_name="og:description")
        if og_desc:
            return og_desc[:500]
        return None

    @staticmethod
    def _extract_meta_tag(
        soup: BeautifulSoup,
        name: Optional[str] = None,
        property_name: Optional[str] = None,
    ) -> Optional[str]:
        """Helper to extract content attribute from a meta tag."""
        tag = None
        if name:
            tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        elif property_name:
            tag = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(property_name)}$", re.I)})

        if tag and tag.get("content"):
            content = tag["content"].strip()
            return content if content else None
        return None

    def _extract_headings(self, soup: BeautifulSoup) -> list[str]:
        """Extract top H1, H2, and H3 headings without excessive repetition."""
        headings: list[str] = []
        seen = set()

        for heading_tag in soup.find_all(["h1", "h2", "h3"]):
            text = " ".join(heading_tag.get_text().split()).strip()
            if text and len(text) >= 3 and text.lower() not in seen:
                seen.add(text.lower())
                headings.append(text[:120])
                if len(headings) >= self.max_headings:
                    break

        return headings

    def _extract_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> tuple[list[DiscoveredLink], Optional[str]]:
        """Extract categorized candidate links and locate high-probability careers URLs."""
        discovered: list[DiscoveredLink] = []
        careers_url: Optional[str] = None
        base_domain = urlparse(base_url).netloc.lower()
        seen_urls = set()

        for a_tag in soup.find_all("a", href=True):
            raw_href = a_tag["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            absolute_url = urljoin(base_url, raw_href).rstrip("/")
            if absolute_url in seen_urls:
                continue

            link_text = " ".join(a_tag.get_text().split()).strip()
            if not link_text and not raw_href:
                continue

            link_domain = urlparse(absolute_url).netloc.lower()
            # Focus on same-domain links or known ATS platforms (greenhouse, lever, ashby, workable)
            is_same_domain = (link_domain == base_domain or link_domain.endswith(f".{base_domain}"))
            is_known_ats = any(ats in link_domain for ats in ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com"))

            if not is_same_domain and not is_known_ats:
                continue

            seen_urls.add(absolute_url)

            # Categorize link
            combined_text = f"{link_text} {raw_href}".lower()
            category = "general"

            if any(k in combined_text for k in self.CAREER_KEYWORDS):
                category = "careers"
                if careers_url is None:
                    careers_url = absolute_url
            elif any(k in combined_text for k in self.ABOUT_KEYWORDS):
                category = "about"
            elif any(k in combined_text for k in self.PRODUCT_KEYWORDS):
                category = "products"

            if category != "general" or len(discovered) < self.max_discovered_links:
                discovered.append(
                    DiscoveredLink(
                        text=link_text[:80] if link_text else raw_href[:80],
                        url=absolute_url,
                        category=category,
                    )
                )

            if len(discovered) >= self.max_discovered_links:
                break

        return discovered, careers_url

    @staticmethod
    def _strip_noise(soup: BeautifulSoup) -> None:
        """Remove comments, scripts, styles, forms, and boilerplate markup."""
        # Remove comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove noisy tags
        noise_tags = [
            "script", "style", "noscript", "iframe", "svg",
            "nav", "footer", "header", "form", "button", "input",
            "select", "textarea", "style", "link",
        ]
        for tag in soup.find_all(noise_tags):
            tag.decompose()

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        """Extract clean, bounded readable text from paragraphs and content blocks."""
        paragraphs = []
        for p in soup.find_all(["p", "article", "section", "li"]):
            text = " ".join(p.get_text().split()).strip()
            if text and len(text) >= 20:  # Skip tiny fragments
                paragraphs.append(text)

        full_text = " \n\n ".join(paragraphs)
        if len(full_text) > self.max_text_length:
            full_text = full_text[: self.max_text_length].rsplit(" ", 1)[0] + "..."

        return full_text
