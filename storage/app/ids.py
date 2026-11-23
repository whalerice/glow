import re
from urllib.parse import urlparse

_NUMERIC = re.compile(r"(\d+)(?:-.*)?\Z")


def person_mdl_id(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    if "://" in text:
        text = urlparse(text).path
    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    text = text.split("/")[-1]
    match = _NUMERIC.fullmatch(text)
    return match.group(1) if match else None


def work_mdl_id(slug: object) -> str | None:
    if not isinstance(slug, str):
        return None
    return person_mdl_id(slug)
