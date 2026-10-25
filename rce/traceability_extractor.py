"""Traceability extractor for the Requirement Collision Engine (RCE).

Inspects Python source files statically using Python's `ast` module.
Extracts functions, methods, and classes containing docstring tags such as `TRACE: REQ-01`.
Supports multiple requirement tags per function, ignores unrelated docstring text,
and safely filters out invalid tags without executing inspected source files.
"""

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union


class TraceabilityExtractionError(Exception):
    """Raised when static traceability extraction encounters an unrecoverable AST or file error."""
    pass


@dataclass(frozen=True)
class TraceItem:
    """Record of a code entity (function, method, or class) linked to requirements."""

    file_path: str
    name: str
    requirement_ids: List[str]
    entity_type: str = "function"  # "function", "method", or "class"
    line_number: int = 0

    @property
    def source_file(self) -> str:
        """Alias for file_path for compatibility."""
        return self.file_path

    @property
    def function_name(self) -> str:
        """Alias for name for compatibility."""
        return self.name

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace item to dictionary representation."""
        return {
            "file_path": self.file_path,
            "name": self.name,
            "requirement_ids": list(self.requirement_ids),
            "entity_type": self.entity_type,
            "line_number": self.line_number,
        }

    def __repr__(self) -> str:
        tags = ", ".join(self.requirement_ids)
        return (
            f"TraceItem({self.file_path}:{self.name} [{self.entity_type}] "
            f"line {self.line_number} -> [{tags}])"
        )


# Regex to detect lines starting with TRACE: tag (case-insensitive)
# Example matches: "TRACE: REQ-01", "trace: REQ-01, REQ-02", "Trace: REQ-04"
_TRACE_TAG_LINE_REGEX = re.compile(
    r"(?:^|[\r\n])\s*(?:TRACE|trace|Trace)\s*:\s*([^\r\n]+)"
)

# Regex to match valid requirement identifier tokens like REQ-01, REQ-10, REQ-999
_REQ_TOKEN_REGEX = re.compile(r"\bREQ-\d+\b", re.IGNORECASE)


def extract_requirement_ids_from_docstring(
    docstring: Optional[str],
    valid_ids: Optional[Set[str]] = None,
) -> List[str]:
    """Extract valid requirement IDs from TRACE tags in a docstring.

    Only lines explicitly prefixed with `TRACE:` are inspected.
    Unrelated docstring prose and invalid requirement tokens are safely ignored.

    Args:
        docstring: Raw docstring string, or None.
        valid_ids: Optional set of allowed requirement IDs for strict filtering.

    Returns:
        Deduplicated list of uppercase requirement IDs in order of discovery.
    """
    if not docstring:
        return []

    found_ids: List[str] = []
    seen: Set[str] = set()

    for line_match in _TRACE_TAG_LINE_REGEX.finditer(docstring):
        trace_payload = line_match.group(1)
        for token in _REQ_TOKEN_REGEX.findall(trace_payload):
            norm_token = token.upper()
            if valid_ids is not None and norm_token not in valid_ids:
                # Token matches REQ pattern but is not in allowed ID set
                continue
            if norm_token not in seen:
                seen.add(norm_token)
                found_ids.append(norm_token)

    return found_ids


class _TraceVisitor(ast.NodeVisitor):
    """AST visitor that collects functions, methods, and classes with TRACE tags."""

    def __init__(
        self,
        file_path: str,
        include_classes: bool = True,
        valid_ids: Optional[Set[str]] = None,
    ) -> None:
        self.file_path = file_path
        self.include_classes = include_classes
        self.valid_ids = valid_ids
        self.items: List[TraceItem] = []
        self._class_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.include_classes:
            docstring = ast.get_docstring(node)
            req_ids = extract_requirement_ids_from_docstring(docstring, self.valid_ids)
            if req_ids:
                self.items.append(
                    TraceItem(
                        file_path=self.file_path,
                        name=node.name,
                        requirement_ids=req_ids,
                        entity_type="class",
                        line_number=node.lineno,
                    )
                )

        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_function_node(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_function_node(node)
        self.generic_visit(node)

    def _process_function_node(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> None:
        docstring = ast.get_docstring(node)
        req_ids = extract_requirement_ids_from_docstring(docstring, self.valid_ids)
        if not req_ids:
            return

        if self._class_stack:
            qualified_name = f"{self._class_stack[-1]}.{node.name}"
            entity_type = "method"
        else:
            qualified_name = node.name
            entity_type = "function"

        self.items.append(
            TraceItem(
                file_path=self.file_path,
                name=qualified_name,
                requirement_ids=req_ids,
                entity_type=entity_type,
                line_number=node.lineno,
            )
        )


def extract_traceability_from_source(
    source_code: str,
    file_path: str = "<string>",
    include_classes: bool = True,
    valid_ids: Optional[Iterable[str]] = None,
) -> List[TraceItem]:
    """Statically extract requirement traceability from Python source code.

    Does not execute the source code.

    Args:
        source_code: Python code string.
        file_path: Display file path for extracted items.
        include_classes: Whether to extract classes with TRACE tags.
        valid_ids: Optional collection of allowed requirement IDs.

    Returns:
        List of TraceItem instances.

    Raises:
        TraceabilityExtractionError: If the source code cannot be parsed by ast.
    """
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as err:
        raise TraceabilityExtractionError(
            f"Syntax error parsing '{file_path}': {err}"
        ) from err

    valid_id_set = {v.upper() for v in valid_ids} if valid_ids is not None else None
    visitor = _TraceVisitor(
        file_path=file_path,
        include_classes=include_classes,
        valid_ids=valid_id_set,
    )
    visitor.visit(tree)
    return visitor.items


def extract_traceability_from_file(
    file_path: Union[str, Path],
    include_classes: bool = True,
    valid_ids: Optional[Iterable[str]] = None,
    relative_to: Optional[Union[str, Path]] = None,
) -> List[TraceItem]:
    """Statically inspect a single Python file for requirement traceability.

    Args:
        file_path: Path to Python source file.
        include_classes: Whether to extract classes with TRACE tags.
        valid_ids: Optional collection of allowed requirement IDs.
        relative_to: Base directory for relative file paths in output.

    Returns:
        List of TraceItem instances.

    Raises:
        FileNotFoundError: If the file does not exist.
        TraceabilityExtractionError: If AST parsing fails.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")

    if relative_to is not None:
        try:
            rel = os.path.relpath(path, start=relative_to).replace("\\", "/")
            display_path = rel
        except ValueError:
            display_path = path.as_posix()
    else:
        # Default to normalized posix representation
        display_path = path.as_posix()

    return extract_traceability_from_source(
        source_code=content,
        file_path=display_path,
        include_classes=include_classes,
        valid_ids=valid_ids,
    )


def extract_traceability_from_directory(
    dir_path: Union[str, Path] = "cews",
    include_classes: bool = True,
    valid_ids: Optional[Iterable[str]] = None,
    recursive: bool = True,
) -> List[TraceItem]:
    """Statically inspect all Python files in a directory for requirement traceability.

    Inspects files without importing or executing them.

    Args:
        dir_path: Path to directory (e.g., 'cews').
        include_classes: Whether to extract classes with TRACE tags.
        valid_ids: Optional collection of allowed requirement IDs.
        recursive: Whether to traverse subdirectories recursively.

    Returns:
        Sorted list of TraceItem instances by file_path and line_number.

    Raises:
        FileNotFoundError: If the directory does not exist.
    """
    root = Path(dir_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root.resolve()}")

    items: List[TraceItem] = []

    pattern = "**/*.py" if recursive else "*.py"
    py_files = sorted(root.glob(pattern), key=lambda p: str(p))

    for py_file in py_files:
        # Exclude pycache and hidden directories
        if "__pycache__" in py_file.parts or any(p.startswith(".") for p in py_file.parts):
            continue

        file_items = extract_traceability_from_file(
            file_path=py_file,
            include_classes=include_classes,
            valid_ids=valid_ids,
            relative_to=root.parent,
        )
        items.extend(file_items)

    # Sort deterministically by file_path and line_number
    items.sort(key=lambda it: (it.file_path, it.line_number, it.name))
    return items


def build_traceability_matrix(
    items: List[TraceItem],
) -> Dict[str, List[TraceItem]]:
    """Group trace items by requirement ID.

    Returns:
        Dict mapping requirement ID (e.g., 'REQ-01') to list of TraceItems.
    """
    matrix: Dict[str, List[TraceItem]] = {}
    for item in items:
        for req_id in item.requirement_ids:
            matrix.setdefault(req_id, []).append(item)
    return matrix


def build_requirement_to_entities_map(
    items: List[TraceItem],
) -> Dict[str, List[str]]:
    """Build a mapping of requirement ID -> list of 'file_path:name' identifiers.

    Returns:
        Dict mapping requirement ID to list of entity specifier strings.
    """
    matrix = build_traceability_matrix(items)
    return {
        req_id: [f"{it.file_path}:{it.name}" for it in trace_items]
        for req_id, trace_items in sorted(matrix.items())
    }
