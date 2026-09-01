"""Factual evidence and dynamic career/job extractor for rendered DOM pages."""

import re
from typing import Any, Optional
from bs4 import BeautifulSoup

from app.enrichment.extractor import HtmlEvidenceExtractor
from app.enrichment.schemas import ExtractedPageFacts


class BrowserEvidenceExtractor:
    """Extracts factual evidence from rendered dynamic DOM with specialized career/job detection."""

    TECH_KEYWORDS = (
        "Python", "FastAPI", "Django", "Flask", "PostgreSQL", "MySQL", "MongoDB",
        "Redis", "Kafka", "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform",
        "React", "Next.js", "Vue", "TypeScript", "Node.js", "GraphQL", "C++", "Rust",
        "Golang", "Java", "PyTorch", "TensorFlow", "Snowflake", "Spark", "ROS2", "Computer Vision"
    )

    def __init__(
        self,
        base_extractor: Optional[HtmlEvidenceExtractor] = None,
        max_jobs_extracted: int = 20,
    ) -> None:
        self.base_extractor = base_extractor or HtmlEvidenceExtractor()
        self.max_jobs_extracted = max_jobs_extracted

    def extract_rendered_page(
        self,
        rendered_html: str,
        page_url: str,
    ) -> tuple[ExtractedPageFacts, dict[str, Any]]:
        """
        Extract base page facts plus specialized dynamic career/job evidence from rendered DOM.
        Returns: (ExtractedPageFacts, career_facts_dict).
        """
        base_facts = self.base_extractor.extract(rendered_html, page_url)
        career_facts = self._extract_career_and_tech_facts(rendered_html, page_url)

        return base_facts, career_facts

    def _extract_career_and_tech_facts(
        self,
        rendered_html: str,
        page_url: str,
    ) -> dict[str, Any]:
        """Inspect rendered DOM for dynamic job cards, hiring departments, and tech stack mentions."""
        soup = BeautifulSoup(rendered_html, "html.parser")

        job_titles: list[str] = []
        departments: dict[str, int] = {}
        locations: set[str] = set()
        tech_detected: set[str] = set()
        remote_friendly = False

        # 1. Search for structured job cards
        job_card_selectors = [
            ".job-card", ".career-card", ".job-listing", ".opening-card",
            "[data-job-id]", "[data-dept]", ".job_item", ".careers-list > div"
        ]

        job_elements = []
        for selector in job_card_selectors:
            matched = soup.select(selector)
            if matched:
                job_elements.extend(matched)

        # 2. Extract job details from detected cards
        for elem in job_elements[: self.max_jobs_extracted]:
            # Extract Title
            title_tag = elem.find(["h3", "h4", "h2", "a", "strong"])
            if title_tag:
                title_text = " ".join(title_tag.get_text().split()).strip()
                if title_text and len(title_text) >= 5 and title_text not in job_titles:
                    job_titles.append(title_text[:100])

            # Extract Department if labeled
            dept_elem = elem.find(class_=re.compile(r"dept|department|category|team", re.I))
            if dept_elem:
                dept_text = " ".join(dept_elem.get_text().split()).strip()
                if dept_text:
                    departments[dept_text] = departments.get(dept_text, 0) + 1

            # Extract Location
            loc_elem = elem.find(class_=re.compile(r"loc|location|city|country", re.I))
            if loc_elem:
                loc_text = " ".join(loc_elem.get_text().split()).strip()
                if loc_text:
                    locations.add(loc_text[:60])

        # 3. Detect technology keywords across the entire rendered page text
        page_text = soup.get_text()
        for tech in self.TECH_KEYWORDS:
            # Custom word boundary handling for tech terms like C++, .NET, Next.js
            pattern = r"(?<!\w)" + re.escape(tech) + r"(?!\w)"
            if re.search(pattern, page_text, re.IGNORECASE):
                tech_detected.add(tech)

        # 4. Detect remote work policies
        if re.search(r"(?<!\w)(remote|hybrid|distributed|work from anywhere)(?!\w)", page_text, re.IGNORECASE):
            remote_friendly = True

        # Total job count from cards or explicit counter
        explicit_count_elem = soup.find(attrs={"data-total-jobs": True}) or soup.find(id=re.compile(r"jobs.*count", re.I))
        active_jobs_count = len(job_titles)
        if explicit_count_elem:
            try:
                count_str = explicit_count_elem.get("data-total-jobs") or explicit_count_elem.get_text()
                parsed_count = int(re.search(r"\d+", count_str).group())
                active_jobs_count = max(active_jobs_count, parsed_count)
            except Exception:
                pass

        return {
            "careers_page_rendered": True,
            "careers_source_url": page_url,
            "active_jobs_count": active_jobs_count,
            "job_titles": job_titles,
            "hiring_departments": departments,
            "locations": list(locations),
            "tech_stack_detected": sorted(list(tech_detected)),
            "remote_friendly": remote_friendly,
        }
