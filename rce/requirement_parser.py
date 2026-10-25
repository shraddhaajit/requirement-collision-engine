"""Requirement parser for the Requirement Collision Engine (RCE).

Parses structured business requirements from markdown documentation (e.g., requirements/requirements.md).
Extracts requirement ID, title, and full description while strictly validating against
missing or malformed entries without hardcoding content or duplicating definitions.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union


class RequirementParseError(ValueError):
    """Raised when parsing requirements fails due to missing, malformed, or invalid entries."""
    pass


@dataclass(frozen=True)
class Requirement:
    """Structured representation of a parsed business requirement."""

    id: str
    title: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        """Return a dictionary representation of the requirement."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
        }

    def __repr__(self) -> str:
        short_desc = self.description.replace("\n", " ")
        if len(short_desc) > 60:
            short_desc = short_desc[:57] + "..."
        return f"Requirement(id={self.id!r}, title={self.title!r}, desc={short_desc!r})"


# Pattern for markdown headings (e.g., "### REQ-01 — Expense Submission" or "### REQ-01: Title")
# Matches heading level (1-6 '#' symbols), requirement tag, delimiter, and title.
_HEADING_LINE_REGEX = re.compile(r"^(#{1,6})\s+(.*)$")
_REQ_TAG_REGEX = re.compile(r"^(REQ-\d+)\b(.*)$", re.IGNORECASE)
_DELIMITER_REGEX = re.compile(r"^[\s—–:\-]+(.*)$")


def parse_requirements_from_text(
    content: str,
    source_name: str = "<string>",
    expected_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Requirement]:
    """Parse requirements from markdown text.

    Args:
        content: Markdown content string.
        source_name: Name of the source (for error messages).
        expected_ids: Optional iterable of requirement IDs that must be present.

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-01') to Requirement instance.

    Raises:
        RequirementParseError: If malformed headers, missing fields, or duplicates are found.
    """
    if not content or not content.strip():
        raise RequirementParseError(f"Requirements content in '{source_name}' is empty.")

    lines = content.splitlines()
    requirements: Dict[str, Requirement] = {}

    current_id: Optional[str] = None
    current_title: Optional[str] = None
    current_desc_lines: List[str] = []
    current_heading_level: Optional[int] = None

    def finalize_current():
        nonlocal current_id, current_title, current_desc_lines, current_heading_level
        if current_id is not None:
            desc = "\n".join(current_desc_lines).strip()
            if not desc:
                raise RequirementParseError(
                    f"Requirement '{current_id}' in '{source_name}' has an empty description."
                )
            if current_id in requirements:
                raise RequirementParseError(
                    f"Duplicate requirement ID detected: '{current_id}' in '{source_name}'."
                )
            requirements[current_id] = Requirement(
                id=current_id,
                title=current_title,
                description=desc,
            )
            current_id = None
            current_title = None
            current_desc_lines = []
            current_heading_level = None

    for line_num, line in enumerate(lines, start=1):
        heading_match = _HEADING_LINE_REGEX.match(line)
        if heading_match:
            heading_hashes, heading_body = heading_match.groups()
            level = len(heading_hashes)
            trimmed_body = heading_body.strip()

            # Check if this heading is a REQ heading
            if trimmed_body.upper().startswith("REQ"):
                # Potential requirement heading
                req_match = _REQ_TAG_REGEX.match(trimmed_body)
                if not req_match:
                    raise RequirementParseError(
                        f"Malformed requirement heading at line {line_num} in '{source_name}': "
                        f"'{line.strip()}'. Expected 'REQ-<digits>'."
                    )

                raw_id, remainder = req_match.groups()
                req_id = raw_id.upper()

                # Parse the title from remainder
                delim_match = _DELIMITER_REGEX.match(remainder)
                if delim_match:
                    title = delim_match.group(1).strip()
                else:
                    title = remainder.strip()

                if not title:
                    raise RequirementParseError(
                        f"Requirement '{req_id}' at line {line_num} in '{source_name}' is missing a title."
                    )

                # Finalize any previously collected requirement
                finalize_current()

                current_id = req_id
                current_title = title
                current_heading_level = level
                current_desc_lines = []
            else:
                # Non-REQ heading.
                # If we are currently collecting a requirement and hit a section heading
                # with equal or higher level (e.g. ## Assumptions after ### REQ-10),
                # this closes the current requirement.
                if current_id is not None and level <= current_heading_level:
                    finalize_current()
        else:
            if current_id is not None:
                current_desc_lines.append(line)

    # Finalize the last requirement at EOF
    finalize_current()

    if not requirements:
        raise RequirementParseError(f"No valid requirement entries found in '{source_name}'.")

    # Validate expected IDs if specified
    if expected_ids is not None:
        expected_set = {eid.upper() for eid in expected_ids}
        found_set = set(requirements.keys())
        missing = expected_set - found_set
        if missing:
            missing_sorted = sorted(missing)
            raise RequirementParseError(
                f"Missing expected requirements in '{source_name}': {', '.join(missing_sorted)}"
            )

    return requirements


def parse_requirements(
    file_path: Union[str, Path] = "requirements/requirements.md",
    expected_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Requirement]:
    """Parse business requirements from a markdown file.

    Args:
        file_path: Path to requirements markdown file.
        expected_ids: Optional iterable of requirement IDs that must be present.

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-01') to Requirement instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        RequirementParseError: If file is malformed or requirements cannot be parsed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Requirements file not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")
    return parse_requirements_from_text(
        content=content,
        source_name=str(path),
        expected_ids=expected_ids,
    )
