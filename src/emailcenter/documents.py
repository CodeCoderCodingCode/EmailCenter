"""OOXML-based DOCX analysis and placeholder generation."""

from __future__ import annotations

from dataclasses import dataclass
import io
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable
import xml.etree.ElementTree as ET
import zipfile


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
W_P = f"{{{WORD_NAMESPACE}}}p"
W_T = f"{{{WORD_NAMESPACE}}}t"
XML_SPACE = f"{{{XML_NAMESPACE}}}space"
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")
SUPPORTED_PARTS = re.compile(
    r"^word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
)


class DocumentError(RuntimeError):
    """Raised when a DOCX cannot be safely read or generated."""


class MissingRequiredValues(DocumentError):
    def __init__(self, placeholders: Iterable[str]):
        self.placeholders = tuple(sorted(set(placeholders)))
        super().__init__("Missing required values for: " + ", ".join(self.placeholders))


@dataclass(frozen=True)
class PlaceholderAnalysis:
    occurrences: dict[str, int]

    @property
    def placeholders(self) -> tuple[str, ...]:
        return tuple(sorted(self.occurrences))


@dataclass(frozen=True)
class GenerationResult:
    output_path: Path
    replaced: dict[str, int]
    unresolved: tuple[str, ...]


def analyze_docx(path: str | Path) -> PlaceholderAnalysis:
    """Count supported placeholders across body, tables, headers, and footers."""
    source = Path(path)
    counts: dict[str, int] = {}
    for part_name, xml_bytes in _read_supported_parts(source):
        root = _parse_xml(xml_bytes, part_name)
        for paragraph in root.iter(W_P):
            text = "".join(node.text or "" for node in _paragraph_text_nodes(paragraph))
            for match in PLACEHOLDER_PATTERN.finditer(text):
                name = match.group(1)
                counts[name] = counts.get(name, 0) + 1
    return PlaceholderAnalysis(counts)


def extract_docx_text(path: str | Path) -> str:
    """Return paragraph text for an explicitly labelled text-only preview."""
    sections: list[str] = []
    for name, content in _read_supported_parts(Path(path)):
        root = _parse_xml(content, name)
        def paragraph_text(element):
            parts = []
            for child in element:
                if child.tag == W_P:
                    continue
                if child.tag == W_T:
                    parts.append(child.text or "")
                elif child.tag in (f"{{{WORD_NAMESPACE}}}br", f"{{{WORD_NAMESPACE}}}cr"):
                    parts.append("\n")
                elif child.tag == f"{{{WORD_NAMESPACE}}}tab":
                    parts.append("\t")
                else:
                    parts.append(paragraph_text(child))
            return "".join(parts)
        paragraphs = [paragraph_text(paragraph) for paragraph in root.iter(W_P)]
        section_name = ("Dokument" if name == "word/document.xml" else
                        "Kopfzeile" if "header" in name else
                        "Fußzeile" if "footer" in name else
                        "Fußnoten" if "footnotes" in name else
                        "Endnoten" if "endnotes" in name else "Kommentare")
        sections.append(section_name + "\n" + "\n".join(paragraphs))
    return "\n\n".join(sections)


def generate_docx(
    template_path: str | Path,
    output_path: str | Path,
    values: dict[str, object],
    *,
    required_placeholders: Iterable[str] = (),
) -> GenerationResult:
    """Generate a DOCX copy, replacing placeholders even across Word runs.

    Replacement text inherits the formatting of the first run of the original
    placeholder. The source template is never modified.
    """
    source = Path(template_path).resolve()
    target = Path(output_path).resolve()
    if source == target:
        raise DocumentError("Generated documents must not overwrite their template.")
    if not source.is_file():
        raise DocumentError(f"DOCX template does not exist: {source}")
    if not zipfile.is_zipfile(source):
        raise DocumentError(f"Template is not a valid DOCX package: {source}")

    normalized_values = _normalize_values(values)
    analysis = analyze_docx(source)
    required = {_normalize_name(name) for name in required_placeholders}
    missing = [name for name in required if not normalized_values.get(name)]
    if missing:
        raise MissingRequiredValues(missing)

    replaced_counts: dict[str, int] = {}
    unresolved: set[str] = set()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent, delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        with zipfile.ZipFile(source, "r") as source_archive:
            with zipfile.ZipFile(temporary_path, "w") as output_archive:
                for entry in source_archive.infolist():
                    content = source_archive.read(entry.filename)
                    if SUPPORTED_PARTS.fullmatch(entry.filename):
                        root = _parse_xml(content, entry.filename)
                        changed = False
                        for paragraph in root.iter(W_P):
                            nodes = _paragraph_text_nodes(paragraph)
                            paragraph_counts, paragraph_unresolved = _replace_in_paragraph(
                                nodes, normalized_values
                            )
                            for key, count in paragraph_counts.items():
                                replaced_counts[key] = replaced_counts.get(key, 0) + count
                            unresolved.update(paragraph_unresolved)
                            changed = changed or bool(paragraph_counts)
                        if changed:
                            serialized = ET.tostring(
                                root, encoding="utf-8", xml_declaration=True,
                                short_empty_elements=True,
                            )
                            content = _restore_namespace_declarations(
                                serialized, _namespace_declarations(content)
                            )
                    output_archive.writestr(entry, content)

        with zipfile.ZipFile(temporary_path, "r") as generated_archive:
            if generated_archive.testzip() is not None:
                raise DocumentError("Generated DOCX archive failed its integrity check.")
            if "word/document.xml" not in generated_archive.namelist():
                raise DocumentError("Generated file is missing word/document.xml.")

        os.replace(temporary_path, target)
    except Exception as error:
        temporary_path.unlink(missing_ok=True)
        if isinstance(error, DocumentError):
            raise
        raise DocumentError(f"Could not generate DOCX: {error}") from error

    remaining_from_analysis = set(analysis.placeholders) - set(replaced_counts)
    unresolved.update(remaining_from_analysis)
    return GenerationResult(
        output_path=target,
        replaced=dict(sorted(replaced_counts.items())),
        unresolved=tuple(sorted(unresolved)),
    )


def _read_supported_parts(path: Path) -> list[tuple[str, bytes]]:
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise DocumentError(f"Not a valid DOCX package: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if "word/document.xml" not in archive.namelist():
                raise DocumentError("DOCX package is missing word/document.xml.")
            parts = [
                (name, archive.read(name))
                for name in archive.namelist()
                if SUPPORTED_PARTS.fullmatch(name)
            ]
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise DocumentError(f"Could not read DOCX package {path}: {error}") from error
    return parts


def _parse_xml(content: bytes, part_name: str) -> ET.Element:
    namespaces = _namespace_declarations(content, part_name)
    for prefix, uri in namespaces:
        if prefix != "xml":
            ET.register_namespace(prefix, uri)
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        return ET.fromstring(content, parser=parser)
    except ET.ParseError as error:
        raise DocumentError(f"Invalid XML in {part_name}: {error}") from error


def _namespace_declarations(
    content: bytes, part_name: str = "DOCX XML"
) -> list[tuple[str, str]]:
    try:
        return [
            namespace
            for _, namespace in ET.iterparse(io.BytesIO(content), events=("start-ns",))
        ]
    except ET.ParseError as error:
        raise DocumentError(f"Invalid XML in {part_name}: {error}") from error


def _restore_namespace_declarations(
    serialized: bytes, namespaces: list[tuple[str, str]]
) -> bytes:
    root_match = re.search(rb"<[^!?][^>]*>", serialized)
    if root_match is None:
        raise DocumentError("Could not serialize DOCX XML root element.")
    root_tag = root_match.group(0)
    missing: list[bytes] = []
    seen_prefixes: set[str] = set()
    for prefix, uri in namespaces:
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        attribute = f"xmlns:{prefix}" if prefix else "xmlns"
        if re.search(rb"\b" + re.escape(attribute.encode("utf-8")) + rb"=", root_tag):
            continue
        escaped_uri = uri.replace("&", "&amp;").replace('"', "&quot;")
        missing.append(f' {attribute}="{escaped_uri}"'.encode("utf-8"))
    if not missing:
        return serialized
    insertion = b"".join(missing)
    updated_root = root_tag[:-2] + insertion + b"/>" if root_tag.endswith(b"/>") else root_tag[:-1] + insertion + b">"
    return serialized[: root_match.start()] + updated_root + serialized[root_match.end() :]


def _paragraph_text_nodes(paragraph: ET.Element) -> list[ET.Element]:
    nodes: list[ET.Element] = []

    def visit(element: ET.Element) -> None:
        for child in element:
            if child.tag == W_P:
                continue
            if child.tag == W_T:
                nodes.append(child)
            visit(child)

    visit(paragraph)
    return nodes


def _normalize_values(values: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        name = _normalize_name(key)
        if not name:
            raise ValueError("Placeholder mapping keys must not be empty.")
        if name in normalized:
            raise ValueError(f"Duplicate placeholder mapping for {name!r}.")
        if value is None:
            normalized[name] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[name] = str(value)
        else:
            raise ValueError(f"Placeholder value for {name!r} must be text or a scalar.")
    return normalized


def _normalize_name(value: str) -> str:
    return value.strip().removeprefix("{{").removesuffix("}}").strip()


def _replace_in_paragraph(
    nodes: list[ET.Element], values: dict[str, str]
) -> tuple[dict[str, int], set[str]]:
    texts = [node.text or "" for node in nodes]
    whole_text = "".join(texts)
    matches = list(PLACEHOLDER_PATTERN.finditer(whole_text))
    counts: dict[str, int] = {}
    unresolved: set[str] = set()

    boundaries: list[tuple[int, int]] = []
    position = 0
    for text in texts:
        boundaries.append((position, position + len(text)))
        position += len(text)

    for match in reversed(matches):
        name = match.group(1)
        replacement = values.get(name)
        if replacement is None:
            unresolved.add(name)
            continue
        start_node, start_offset = _locate_character(boundaries, match.start())
        end_node, end_offset = _locate_character(boundaries, match.end() - 1)
        end_offset += 1
        if start_node == end_node:
            texts[start_node] = (
                texts[start_node][:start_offset] + replacement + texts[end_node][end_offset:]
            )
        else:
            texts[start_node] = texts[start_node][:start_offset] + replacement
            for index in range(start_node + 1, end_node):
                texts[index] = ""
            texts[end_node] = texts[end_node][end_offset:]
        counts[name] = counts.get(name, 0) + 1

    for node, text in zip(nodes, texts):
        node.text = text
        if text[:1].isspace() or text[-1:].isspace():
            node.set(XML_SPACE, "preserve")
    return counts, unresolved


def _locate_character(boundaries: list[tuple[int, int]], position: int) -> tuple[int, int]:
    for index, (start, end) in enumerate(boundaries):
        if start <= position < end:
            return index, position - start
    raise DocumentError("Placeholder text could not be mapped to document runs.")

