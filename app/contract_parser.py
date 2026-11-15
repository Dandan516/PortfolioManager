from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _TextHTMLParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__()
		self.parts: list[str] = []
		self._ignored_tags: list[str] = []

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag.casefold() in {"script", "style"}:
			self._ignored_tags.append(tag.casefold())

	def handle_endtag(self, tag: str) -> None:
		if self._ignored_tags and self._ignored_tags[-1] == tag.casefold():
			self._ignored_tags.pop()

	def handle_data(self, data: str) -> None:
		if not self._ignored_tags and data.strip():
			self.parts.append(data.strip())


def read_contract_file(path: Path) -> str:
	"""Read supported contract formats and return plain text for the LLM."""
	suffix = path.suffix.casefold()
	if suffix in {".txt", ".html", ".htm"}:
		content = path.read_text(encoding="utf-8", errors="replace")
		if suffix in {".html", ".htm"}:
			parser = _TextHTMLParser()
			parser.feed(content)
			content = "\n".join(parser.parts)
	elif suffix == ".pdf":
		content = _read_pdf(path)
	else:
		raise ValueError(f"Unsupported contract format: {path.suffix or 'unknown'}")

	if not content.strip():
		raise ValueError(f"No readable text found in {path.name}")
	return content


def _read_pdf(path: Path) -> str:
	try:
		from pypdf import PdfReader
	except ImportError as exc:
		raise RuntimeError("PDF support requires the pypdf package.") from exc

	reader = PdfReader(str(path))
	pages = [page.extract_text() or "" for page in reader.pages]
	return "\n\n".join(pages)
