import re

EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
)

def is_valid_email(raw: str) -> bool:
    return EMAIL_RE.fullmatch(raw) is not None

def find_email(text: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for match in EMAIL_RE.finditer(text)
    ]