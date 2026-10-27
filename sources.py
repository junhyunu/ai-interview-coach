"""업로드 파일 · 링크에서 글자만 뽑는다. (AI 호출 없음)"""

import io
import re
import urllib.request
from html.parser import HTMLParser

MAX_URL_BYTES = 2_000_000


def read_upload(file) -> str:
    """Streamlit UploadedFile → 텍스트. pdf · docx · txt · md 지원."""
    name = file.name.lower()
    data = file.getvalue()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


class _TextOnly(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def fetch_url(url: str) -> tuple[str, str]:
    """(본문, 에러 문장). 실패하면 본문은 빈 글."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (interview-coach)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read(MAX_URL_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
    except Exception:
        return "", "링크를 열지 못했어요. 공고 내용을 직접 붙여 넣어 주세요."

    parser = _TextOnly()
    parser.feed(raw.decode(charset, errors="ignore"))
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    if len(text) < 200:
        return "", "링크에서 읽을 글이 거의 없어요(로그인 · 동적 페이지일 수 있어요). 공고를 직접 붙여 넣어 주세요."
    return text, ""
