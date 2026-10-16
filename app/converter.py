"""Convert documents to Markdown and measure the token change.

Markdown keeps headings, lists, tables, and links. Nothing is summarized.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import zipfile

import tiktoken

MAX_BYTES = 25 * 1024 * 1024

TEXT_EXTENSIONS = {".html", ".htm", ".csv", ".json", ".xml"}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
VISUAL_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".docx", ".pptx", ".xlsx"}
PNG_NORMALIZED = {".gif", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | OFFICE_EXTENSIONS | IMAGE_EXTENSIONS | {
    ".pdf",
    ".xls",
}

IMAGE_PROMPT = (
    "Describe this image completely for someone who cannot see it. "
    "Include all visible text, numbers, labels, and relationships. "
    "Do not summarize or omit details."
)

_ENCODER = tiktoken.get_encoding("cl100k_base")
_ENGINES: dict[bool, object] = {}


class ConversionError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class Conversion:
    filename: str
    extension: str
    markdown: str
    source_tokens: int | None
    markdown_tokens: int
    savings_pct: float | None
    warning: str | None

    def as_dict(self) -> dict:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "markdown": self.markdown,
            "source_tokens": self.source_tokens,
            "markdown_tokens": self.markdown_tokens,
            "savings_pct": self.savings_pct,
            "warning": self.warning,
        }


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def safe_name(filename: str) -> str:
    name = Path(filename or "upload").name.replace("\x00", "").strip()
    if not name or name in {".", ".."}:
        return "upload"
    return name


def baseline_text(extension: str, data: bytes) -> str | None:
    """Text we would otherwise send to a model, before Markdown conversion.

    Images return None because they have no text baseline.
    """
    text, _warning = source_baseline(extension, data)
    return text


def source_baseline(extension: str, data: bytes) -> tuple[str | None, str | None]:
    ext = extension.lower()
    if ext in IMAGE_EXTENSIONS:
        return None, None
    if ext in TEXT_EXTENSIONS:
        return data.decode("utf-8", errors="replace"), None
    if ext in OFFICE_EXTENSIONS:
        return _office_xml(data, ext)
    if ext == ".pdf":
        return _pdf_text(data)
    if ext == ".xls":
        return _xls_text(data)
    raise ConversionError(f"{ext} is not a supported file type.")


def convert_bytes(filename: str, data: bytes) -> Conversion:
    name = safe_name(filename)
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ConversionError(
            f"{extension or 'This file type'} is not supported. "
            "Use PDF, Word, PowerPoint, Excel, HTML, CSV, JSON, XML, or an image."
        )
    if len(data) > MAX_BYTES:
        raise ConversionError("Files must be 25 MB or smaller.")
    if not data:
        raise ConversionError("The file is empty.")

    warnings: list[str] = []
    baseline, baseline_warning = source_baseline(extension, data)
    if baseline_warning:
        warnings.append(baseline_warning)

    payload, payload_ext, prep_warning = _prepare_payload(extension, data)
    if prep_warning:
        warnings.append(prep_warning)

    markdown, convert_warning = _to_markdown(name, payload, payload_ext)
    if convert_warning:
        warnings.append(convert_warning)
    if not _model_configured() and extension in VISUAL_EXTENSIONS:
        if extension in IMAGE_EXTENSIONS:
            warnings.append("LLMHUB_MODEL is not set, so this image was not described.")
        else:
            warnings.append(
                "LLMHUB_MODEL is not set, so pictures inside the file were not described. "
                "The document text was still converted."
            )
    markdown = _tighten(markdown)
    if not markdown:
        warnings.append("No text could be extracted from this file.")

    source_tokens = count_tokens(baseline) if baseline is not None else None
    markdown_tokens = count_tokens(markdown)
    return Conversion(
        filename=name,
        extension=extension,
        markdown=markdown,
        source_tokens=source_tokens,
        markdown_tokens=markdown_tokens,
        savings_pct=_savings(source_tokens, markdown_tokens),
        warning=" ".join(warnings) or None,
    )


def _savings(source_tokens: int | None, markdown_tokens: int) -> float | None:
    if source_tokens is None or source_tokens <= 0:
        return None
    return round((source_tokens - markdown_tokens) / source_tokens * 100, 1)


def _tighten(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _prepare_payload(extension: str, data: bytes) -> tuple[bytes, str, str | None]:
    """Turn extra image types into PNG so MarkItDown can describe them."""
    if extension not in PNG_NORMALIZED:
        return data, extension, None
    try:
        from PIL import Image
    except ImportError as exc:
        raise ConversionError("Image conversion needs Pillow.") from exc

    try:
        with Image.open(BytesIO(data)) as image:
            frames = getattr(image, "n_frames", 1)
            if getattr(image, "is_animated", False):
                image.seek(0)
            converted = image.convert("RGB")
            out = BytesIO()
            converted.save(out, format="PNG")
    except Exception as exc:
        raise ConversionError("The image could not be read.") from exc

    warning = None
    if frames > 1:
        warning = "Only the first frame was described."
    return out.getvalue(), ".png", warning


def _model_configured() -> bool:
    client, model = _llm()
    return client is not None and model is not None


def _llm():
    from app.config import env

    key = env("LLMHUB_API_KEY")
    base_url = env("LLMHUB_BASE_URL")
    model = env("LLMHUB_MODEL")
    if not key or not base_url or not model:
        return None, None
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=base_url, max_retries=2)
    return client, model


def _engine(use_llm: bool):
    cached = _ENGINES.get(use_llm)
    if cached is not None:
        return cached

    from markitdown import MarkItDown

    kwargs: dict = {"enable_plugins": True}
    if use_llm:
        client, model = _llm()
        kwargs["llm_client"] = client
        kwargs["llm_model"] = model
        kwargs["llm_prompt"] = IMAGE_PROMPT
    try:
        engine = MarkItDown(**kwargs)
    except Exception:
        kwargs["enable_plugins"] = False
        engine = MarkItDown(**kwargs)
    _ENGINES[use_llm] = engine
    return engine


def _to_markdown(filename: str, data: bytes, extension: str) -> tuple[str, str | None]:
    use_llm = _model_configured()
    try:
        return _run(filename, data, extension, use_llm), None
    except Exception:
        if not use_llm:
            raise
        try:
            markdown = _run(filename, data, extension, False)
        except Exception as exc:
            raise ConversionError("The file could not be converted.") from exc
        return markdown, (
            "Image description was skipped because the model call failed. "
            "The document text was still converted."
        )


def _run(filename: str, data: bytes, extension: str, use_llm: bool) -> str:
    from markitdown import FileConversionException, StreamInfo, UnsupportedFormatException

    stream_name = filename
    if extension == ".png" and not filename.lower().endswith(".png"):
        stream_name = f"{Path(filename).stem}.png"
    try:
        result = _engine(use_llm).convert_stream(
            BytesIO(data),
            stream_info=StreamInfo(extension=extension, filename=stream_name),
        )
    except (FileConversionException, UnsupportedFormatException) as exc:
        raise ConversionError("The file could not be converted.") from exc
    return result.markdown or ""


def _office_xml(data: bytes, extension: str) -> tuple[str, str | None]:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        return "", "Office XML could not be read, so there is no source token baseline."

    names = archive.namelist()
    chosen = [name for name in names if _is_content_xml(name, extension)]
    if not chosen:
        chosen = [
            name
            for name in names
            if name.endswith(".xml")
            and not name.endswith(".rels")
            and "theme" not in name.lower()
            and name != "[Content_Types].xml"
        ]
    chunks = []
    for name in chosen:
        chunks.append(archive.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks), None


def _is_content_xml(name: str, extension: str) -> bool:
    lower = name.lower()
    if extension == ".docx":
        return lower in {
            "word/document.xml",
            "word/footnotes.xml",
            "word/endnotes.xml",
            "word/comments.xml",
            "word/numbering.xml",
        } or lower.startswith("word/header") or lower.startswith("word/footer")
    if extension == ".pptx":
        return lower.startswith("ppt/slides/slide") or lower.startswith(
            "ppt/notesslides/"
        )
    if extension == ".xlsx":
        return lower == "xl/sharedstrings.xml" or lower.startswith("xl/worksheets/sheet")
    return False


def _pdf_text(data: bytes) -> tuple[str, str | None]:
    try:
        from pdfminer.high_level import extract_text
    except ImportError as exc:
        raise ConversionError("PDF conversion needs pdfminer.six.") from exc
    try:
        return extract_text(BytesIO(data)) or "", None
    except Exception:
        return "", "PDF text could not be read, so there is no source token baseline."


def _xls_text(data: bytes) -> tuple[str, str | None]:
    try:
        import xlrd
    except ImportError as exc:
        raise ConversionError("Excel .xls conversion needs xlrd.") from exc
    try:
        book = xlrd.open_workbook(file_contents=data)
    except Exception:
        return "", "The spreadsheet could not be read, so there is no source token baseline."

    lines = []
    for sheet in book.sheets():
        lines.append(f"sheet:{sheet.name} rows:{sheet.nrows} cols:{sheet.ncols}")
        for row in range(sheet.nrows):
            for col in range(sheet.ncols):
                cell = sheet.cell(row, col)
                lines.append(
                    f"{sheet.name}!R{row + 1}C{col + 1} type={cell.ctype} value={cell.value}"
                )
    return "\n".join(lines), None
