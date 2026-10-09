"""Composer submissions become chat messages (spec FR-022, FR-023, FR-023a)."""

from types import SimpleNamespace

from ui.chat import reply_to, submission_parts


class UntouchableUpload:
    """An uploaded file whose content must never be read (FR-023: the PDF is not stored)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def read(self, *_args: object) -> bytes:
        raise AssertionError("the PDF content was read")

    getvalue = read


def test_text_gets_the_spec_02_placeholder() -> None:
    """VC-027: text → user message with the text, then an assistant placeholder mentioning spec 02."""
    user, assistant = reply_to("hello", [])
    assert user == {"role": "user", "content": "hello"}
    assert assistant["role"] == "assistant"
    assert "spec 02" in assistant["content"]
    assert "spec 01" not in assistant["content"]


def test_pdf_gets_the_spec_01_placeholder() -> None:
    """VC-028: a PDF → user message shows its name; assistant placeholder mentions spec 01."""
    user, assistant = reply_to("", ["report.pdf"])
    assert "report.pdf" in user["content"]
    assert "spec 01" in assistant["content"]
    assert "spec 02" not in assistant["content"]


def test_text_and_pdf_together_get_both_placeholders_in_order() -> None:
    """VC-028a: text + PDF → one user message with both; reply has spec 01 then spec 02."""
    user, assistant = reply_to("what is this?", ["report.pdf"])
    assert "what is this?" in user["content"] and "report.pdf" in user["content"]
    assert assistant["content"].index("spec 01") < assistant["content"].index("spec 02")


def test_submission_parts_use_file_names_only() -> None:
    """VC-028: only the file name is used; the content is never read, so nothing is stored."""
    submission = SimpleNamespace(text="what is this?", files=[UntouchableUpload("report.pdf")])
    assert submission_parts(submission) == ("what is this?", ["report.pdf"])


def test_submission_parts_accept_text_only() -> None:
    """FR-022: a text-only submission has no files."""
    assert submission_parts(SimpleNamespace(text="hello", files=[])) == ("hello", [])
