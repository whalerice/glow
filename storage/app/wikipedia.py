import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from app.agency import parse_agent

BASE_URL = "https://en.wikipedia.org"
SOURCE = "en_wikipedia"
_API = BASE_URL + "/w/api.php"
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 600
_NEXT_CALL = 0.0
_BUSY = "영어 위키가 요청을 잠시 막았습니다. 조금 뒤 다시 고르세요"

_HEADING = re.compile(r"^(=+)([^=\n].*?)\1[ \t]*$", re.M)
_FIELD = re.compile(r"^[ \t]*\|[ \t]*([A-Za-z0-9_]+)[ \t]*=[ \t]*(.*)$", re.M)
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_REF = re.compile(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", re.S)

OVERLAP = {
    "birth_name": "birth_name",
    "native_name": "native_name",
    "birthday": "birthday",
    "birth_place": "birth_place",
    "height": "height",
    "years_active": "years_active",
}
SECTIONS = ("career", "fashion", "ambassadorship", "accolades")


def search(query: str, limit: int = 4) -> list[dict]:
    profiles = []
    busy = None
    for title in _search_titles(query):
        try:
            profile = fetch_page(title)
        except _Busy as exc:
            busy = exc
            break
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        if profile is None:
            continue
        profiles.append(profile)
        if len(profiles) >= limit:
            break
    if not profiles and busy is not None:
        raise busy
    return profiles


def fetch_page(title: str) -> dict | None:
    page = _page_title(title)
    wikitext = _wikitext(page)
    fields = _infobox(wikitext)
    if not fields:
        return None
    profile = {
        "title": page,
        "name": _plain(fields.get("name")) or page,
        "url": f"{BASE_URL}/wiki/{urllib.parse.quote(page.replace(' ', '_'))}",
        "birth_name": _plain(fields.get("birth_name")),
        "native_name": _plain(fields.get("native_name")),
        "birthday": _birthday(fields.get("birth_date", "")),
        "birth_place": _plain(fields.get("birth_place")),
        "height": _height(fields.get("height", "")),
        "education": _plain(fields.get("education")),
        "years_active": _plain(fields.get("years_active")),
        "image_url": _image_url(fields.get("image")),
        "agent": parse_agent(_agent_text(wikitext)),
        "career": _prose(_section(wikitext, "career", 2, skip="fashion")),
        "fashion": _prose(_section(wikitext, "fashion")),
        "ambassadorship": _lines(_section(wikitext, "ambassador", 2)),
        "accolades": _lines(_section(wikitext, "accolade", 2) or _section(wikitext, "awards", 2)),
    }
    if not any(profile.get(key) for key in (
        "birth_name", "native_name", "birthday", "birth_place", "height",
        "education", "years_active", "agent", *SECTIONS,
    )):
        return None
    return profile


def gaps(gmmtv_payload: dict | None) -> set[str]:
    payload = gmmtv_payload if isinstance(gmmtv_payload, dict) else {}
    missing = {"education", "career", "fashion", "ambassadorship", "accolades", "image", "agent"}
    for wiki_key, fandom_key in OVERLAP.items():
        if not _filled(payload, fandom_key):
            missing.add(wiki_key)
    return missing


def selected_payload(profile: dict, fields: list[str], allowed: set[str]) -> dict:
    chosen = [field for field in fields if field in allowed and field in {
        *OVERLAP, "education", *SECTIONS, "image", "agent",
    }]
    if not chosen:
        raise ValueError("넣을 항목을 하나 이상 고르세요")
    payload: dict = {"url": profile["url"]}
    for key in (
        "birth_name", "native_name", "birthday", "birth_place", "height",
        "education", "years_active", "career", "fashion", "ambassadorship", "accolades",
    ):
        if key in chosen and profile.get(key):
            payload[key] = profile[key]
    if "image" in chosen and profile.get("image_url"):
        payload["image_url"] = profile["image_url"]
    if "agent" in chosen and profile.get("agent"):
        payload["agent"] = profile["agent"]
    if len(payload) == 1:
        raise ValueError("고른 항목에 값이 없습니다")
    return payload


def _filled(payload: dict, key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, str) and bool(value.strip())


def _image_url(raw: str | None) -> str | None:
    name = _file_name(raw)
    if name is None:
        return None
    try:
        body = _api({
            "action": "query",
            "titles": f"File:{name}",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        })
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    pages = body.get("query", {}).get("pages", {}) if isinstance(body, dict) else {}
    if not isinstance(pages, dict):
        return None
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info = page.get("imageinfo") or []
        if not info or not isinstance(info[0], dict):
            continue
        url = info[0].get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url.split("?", 1)[0]
    return None


def _file_name(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^\[\[(?:File|Image):", "", text, flags=re.I)
    text = text.split("|", 1)[0].split("]]", 1)[0].strip()
    text = re.sub(r"^(?:File|Image):", "", text, flags=re.I).strip()
    return text or None


def _search_titles(query: str) -> list[str]:
    body = _api({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 8,
        "format": "json",
    })
    hits = body.get("query", {}).get("search", []) if isinstance(body, dict) else []
    titles = []
    for hit in hits:
        title = hit.get("title") if isinstance(hit, dict) else None
        if isinstance(title, str) and "/" not in title:
            titles.append(title)
    return titles


def _infobox(wikitext: str) -> dict[str, str]:
    start = wikitext.find("{{Infobox person")
    if start < 0:
        return {}
    depth = 0
    index = start
    end = start
    while index < len(wikitext):
        if wikitext.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if wikitext.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                end = index
                break
            continue
        index += 1
    return {key: value.strip() for key, value in _FIELD.findall(wikitext[start:end])}


def _agent_text(wikitext: str) -> str:
    start = wikitext.find("{{Infobox person")
    if start < 0:
        return ""
    depth = 0
    index = start
    end = start
    while index < len(wikitext):
        if wikitext.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if wikitext.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                end = index
                break
            continue
        index += 1
    lines = []
    capture = False
    for line in wikitext[start:end].splitlines():
        if not capture:
            match = re.match(r"^[ \t]*\|[ \t]*agent[ \t]*=[ \t]*(.*)$", line)
            if match:
                capture = True
                lines.append(match.group(1))
            continue
        if re.match(r"^[ \t]*\|[ \t]*[A-Za-z0-9_]+[ \t]*=", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _section(wikitext: str, prefix: str, level: int | None = None, skip: str | None = None) -> str:
    matches = list(_HEADING.finditer(wikitext))
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        current = len(match.group(1))
        if level is not None and current != level:
            continue
        if not title.lower().startswith(prefix):
            continue
        end = len(wikitext)
        for later in matches[index + 1:]:
            if len(later.group(1)) <= current:
                end = later.start()
                break
        body = wikitext[match.end():end]
        if skip:
            body = _cut_nested(body, skip)
        return body
    return ""


def _cut_nested(text: str, prefix: str) -> str:
    matches = list(_HEADING.finditer(text))
    for index, match in enumerate(matches):
        if not match.group(2).strip().lower().startswith(prefix):
            continue
        level = len(match.group(1))
        end = len(text)
        for later in matches[index + 1:]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        return text[:match.start()] + text[end:]
    return text


def _prose(section: str) -> str | None:
    text = _strip(section)
    lines = []
    for line in text.splitlines():
        if line.startswith(("{|", "|}", "|-", "|", "!")):
            continue
        line = re.sub(r"\s+", " ", line).strip(" *")
        if line:
            lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned or None


def _lines(section: str) -> str | None:
    rows = []
    for row in re.split(r"\n\|-", section)[1:]:
        cells = []
        for cell in re.split(r"\n\|", row):
            cell = re.sub(r'^\s*(?:rowspan|colspan)\s*=\s*"[^"]*"\s*\|?', "", cell.split("\n", 1)[0], flags=re.I)
            cell = re.sub(r"<ref\b.*", "", cell)
            text = _plain(cell)
            if text:
                cells.append(text)
        if len(cells) >= 2 and re.search(r"\d{4}", cells[0]):
            rows.append(" · ".join(cells[:4]))
    if rows:
        return "\n".join(rows)
    return _prose(section)


def _birthday(raw: str) -> str | None:
    match = re.search(r"(\d{4})\|(\d{1,2})\|(\d{1,2})", raw)
    if match is None:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _height(raw: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*cm", raw)
    if match:
        return f"{match.group(1)} cm"
    metric = re.search(r"m=(\d+(?:\.\d+)?)", raw)
    if metric is None:
        return None
    centimeters = round(float(metric.group(1)) * 100)
    return f"{centimeters} cm"


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    text = _strip(value)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text or None


def _strip(value: str) -> str:
    text = _REF.sub("", value)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\{\{lang\|[^|]+\|([^{}]+)\}\}", r"\1", text)
    text = _drop_templates(text)
    text = _LINK.sub(r"\1", text)
    text = text.replace("<br />", " ").replace("<br>", " ")
    text = re.sub(r"'{2,}", "", text)
    return text


def _drop_templates(text: str) -> str:
    output = []
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            depth = 0
            cursor = index
            while cursor < len(text):
                if text.startswith("{{", cursor):
                    depth += 1
                    cursor += 2
                    continue
                if text.startswith("}}", cursor):
                    depth -= 1
                    cursor += 2
                    if depth == 0:
                        break
                    continue
                cursor += 1
            index = cursor
            continue
        output.append(text[index])
        index += 1
    return "".join(output)


def _page_title(title: str) -> str:
    text = " ".join((title or "").split())
    if not text or any(char in text for char in "|{}[]#<>"):
        raise ValueError("위키 문서 제목이 아닙니다")
    return text


def _wikitext(title: str) -> str:
    body = _api({"action": "parse", "page": title, "prop": "wikitext", "format": "json"})
    parse = body.get("parse") if isinstance(body, dict) else None
    text = parse.get("wikitext") if isinstance(parse, dict) else None
    if isinstance(text, dict):
        text = text.get("*")
    if not isinstance(text, str):
        raise ValueError("위키 문서를 읽지 못했습니다")
    return text


class _Busy(ValueError):
    pass


def _api(params: dict) -> dict:
    key = urllib.parse.urlencode(sorted((name, str(value)) for name, value in params.items()))
    cached = _CACHE.get(key)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]
    body = _load(params)
    if isinstance(body, dict) and body.get("error"):
        info = body["error"].get("info") if isinstance(body["error"], dict) else "위키 오류"
        raise ValueError(str(info))
    if isinstance(body, dict):
        _CACHE[key] = (time.monotonic(), body)
    return body


def _load(params: dict) -> dict:
    global _NEXT_CALL
    delay = 2
    for attempt in range(3):
        gap = _NEXT_CALL - time.monotonic()
        if gap > 0:
            time.sleep(gap)
        request = urllib.request.Request(
            f"{_API}?{urllib.parse.urlencode(params)}",
            headers={
                "User-Agent": os.environ.get(
                    "HTTP_USER_AGENT",
                    "glow-collect/0.1 (local actor collection)",
                )
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.load(response)
            _NEXT_CALL = time.monotonic() + 0.6
            return body
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                if exc.code == 429:
                    raise _Busy(_BUSY) from exc
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            wait = int(retry_after) if retry_after and retry_after.isdigit() else delay
            wait = min(max(wait, 1), 8)
            _NEXT_CALL = time.monotonic() + wait
            time.sleep(wait)
            delay = min(delay * 2, 8)
