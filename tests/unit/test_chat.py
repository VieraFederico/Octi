"""Composer submissions become chat messages (spec FR-022, FR-023, FR-023a)."""

from types import SimpleNamespace

from ui.chat import reply_to, submission_parts


class MemoryUpload:
    """A PDF available as bytes without any filesystem operation (FR-101)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def read(self, *_args: object) -> bytes:
        return b"fixture pdf"

    getvalue = read


def test_text_gets_the_spec_02_placeholder() -> None:
    """VC-027: text → user message with the text, then an assistant placeholder mentioning spec 02."""
    user, assistant = reply_to("hello", [])
    assert user == {"role": "user", "content": "hello"}
    assert assistant["role"] == "assistant"
    assert "spec 02" in assistant["content"]
    assert "spec 01" not in assistant["content"]


def test_submission_parts_keep_pdf_bytes_in_memory() -> None:
    """VC-101/104 smoke supersedes VC-028/028a: text and a PDF reach ingestion together."""
    # Given
    submission = SimpleNamespace(text="what is this?", files=[MemoryUpload("report.pdf")])
    # When
    parts = submission_parts(submission)
    # Then
    assert parts == ("what is this?", [{"name": "report.pdf", "pdf": b"fixture pdf"}])


def test_submission_parts_accept_text_only() -> None:
    """FR-022: a text-only submission has no files."""
    assert submission_parts(SimpleNamespace(text="hello", files=[])) == ("hello", [])
