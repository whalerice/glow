import os
import re
import unicodedata
import urllib.parse

import wikipediaapi

from app.agency import parse_agent

SOURCE = "en_wikipedia"
_BUSY = "위키가 요청을 잠시 막았습니다. 조금 뒤 다시 고르세요"
_WIKIS: dict[str, wikipediaapi.Wikipedia] = {}
_EXTRA = ("fr",)  # ponytail: fr only. add th/id/zh when a page exists only there
_WIKI_URL = re.compile(
    r"(?:https?://)?([a-z]{2,3})\.wikipedia\.org/wiki/([^?#\s]+)",
    re.I,
)
_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_ALIASES = {
    "date de naissance": "birth_date",
    "lieu de naissance": "birth_place",
    "nom de naissance": "birth_name",
    "nom": "name",
    "université / formation": "education",
    "années d'activité": "years_active",
    "taille": "height",
}

_HEADING = re.compile(r"^(=+)([^=\n].*?)\1[ \t]*$", re.M)
_FIELD = re.compile(r"^[ \t]*\|[ \t]*([^=\n|]+?)[ \t]*=[ \t]*(.*)$", re.M)
_PERSON_BOX = re.compile(r"\{\{Infobox (?:person|pageant titleholder|biographie2)\b", re.I)
_THAI = re.compile(r"[\u0e00-\u0e7f][\u0e00-\u0e7f ]*")
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
    located = _wiki_url(query)
    if located:
        title, language = located
        try:
            profile = fetch_page(title, language)
        except _Busy:
            raise
        except (TimeoutError, ValueError):
            return []
        return [profile] if profile else []
    profiles, busy = _collect(query, "en", limit)
    if profiles:
        return profiles
    if busy is not None:
        raise busy
    for language in _EXTRA:
        more, busy = _collect(query, language, limit - len(profiles))
        profiles.extend(more)
        if len(profiles) >= limit:
            break
        if busy is not None:
            raise busy
    return profiles


def fetch_page(title: str, language: str = "en") -> dict | None:
    language = _language(language)
    page = _page(_page_title(title), language)
    if page is None:
        return None
    resolved = page.title or title
    wikitext = _wikitext(resolved, language)
    fields = _infobox(wikitext)
    if not fields:
        return None
    profile = {
        "language": language,
        "title": resolved,
        "name": _plain(fields.get("name")) or resolved,
        "url": page.fullurl,
        "birth_name": _plain(fields.get("birth_name")),
        "native_name": _plain(fields.get("native_name")),
        "birthday": _birthday(fields.get("birth_date", "")) or _birthday(wikitext.split("\n==", 1)[0]),
        "birth_place": _plain(fields.get("birth_place")),
        "height": _height(fields.get("height", "")),
        "education": _plain(fields.get("education")),
        "years_active": _plain(fields.get("years_active")),
        "image_url": _image_url(page, fields.get("image")),
        "agent": parse_agent(_agent_text(wikitext)),
        "career": (
            _prose(_section(wikitext, "career", 2, skip="fashion"))
            or _prose(_section(wikitext, "carriere", 2))
            or _prose(_section(wikitext, "biographie", 2))
        ),
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


def _image_url(page: wikipediaapi.WikipediaPage, raw: str | None) -> str | None:
    name = _file_name(raw)
    if name is None:
        return None
    want = name.casefold()
    try:
        images = page.images.values()
    except wikipediaapi.WikipediaException:
        return None
    for image in images:
        title = (image.title or "").split(":", 1)[-1].casefold()
        if title != want:
            continue
        try:
            url = image.url
        except wikipediaapi.WikipediaException:
            return None
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


def _collect(query: str, language: str, limit: int) -> tuple[list[dict], Exception | None]:
    profiles = []
    busy = None
    for title in _search_titles(query, language):
        try:
            profile = fetch_page(title, language)
        except _Busy as exc:
            busy = exc
            break
        except (TimeoutError, ValueError):
            continue
        if profile is None:
            continue
        profiles.append(profile)
        if len(profiles) >= limit:
            break
    return profiles, busy


def _wiki_url(query: str) -> tuple[str, str] | None:
    match = _WIKI_URL.search((query or "").strip())
    if match is None:
        return None
    title = urllib.parse.unquote(match.group(2)).replace("_", " ")
    return title, match.group(1).lower()


def _search_titles(query: str, language: str) -> list[str]:
    try:
        found = _client(language).search(query, limit=8)
    except wikipediaapi.WikiRateLimitError as exc:
        raise _Busy(_BUSY) from exc
    except wikipediaapi.WikipediaException as exc:
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
    return [title for title in found.pages if isinstance(title, str) and "/" not in title]


def _infobox(wikitext: str) -> dict[str, str]:
    box = _person_box(wikitext)
    if not box:
        return {}
    raw = {key.strip().casefold(): value.strip() for key, value in _FIELD.findall(box)}
    fields = {_ALIASES.get(key, key): value for key, value in raw.items()}
    if not fields.get("native_name"):
        thai = _THAI.search(raw.get("légende", ""))
        if thai:
            fields["native_name"] = thai.group(0).strip()
    return fields


def _person_box(wikitext: str) -> str:
    match = _PERSON_BOX.search(wikitext)
    if match is None:
        return ""
    start = match.start()
    depth = 0
    index = start
    while index < len(wikitext):
        if wikitext.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if wikitext.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                return wikitext[start:index]
            continue
        index += 1
    return ""


def _agent_text(wikitext: str) -> str:
    box = _person_box(wikitext)
    if not box:
        return ""
    lines = []
    capture = False
    for line in box.splitlines():
        if not capture:
            match = re.match(r"^[ \t]*\|[ \t]*(?:agent|agence)[ \t]*=[ \t]*(.*)$", line, re.I)
            if match:
                capture = True
                lines.append(match.group(1))
            continue
        if re.match(r"^[ \t]*\|[ \t]*[A-Za-z0-9_]+[ \t]*=", line):
            break
        lines.append(line)
    return "\n".join(lines).strip().replace("présent", "present").replace("Présent", "present")


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in stripped if unicodedata.category(char) != "Mn")


def _section(wikitext: str, prefix: str, level: int | None = None, skip: str | None = None) -> str:
    matches = list(_HEADING.finditer(wikitext))
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        current = len(match.group(1))
        if level is not None and current != level:
            continue
        if not _fold(title).startswith(_fold(prefix)):
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
        if not _fold(match.group(2)).startswith(_fold(prefix)):
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
        if line.startswith(("{|", "|}", "|-", "|", "!", "=")):
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
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    written = re.search(r"(\d{1,2})\s+([^\s|{}]+)\s+(\d{4})", raw)
    if written is None:
        return None
    day, month_name, year = written.groups()
    month = _FR_MONTHS.get(month_name.casefold())
    if month is None:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _height(raw: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*cm", raw)
    if match:
        return f"{match.group(1)} cm"
    metric = re.search(r"m=(\d+(?:\.\d+)?)", raw) or re.search(r"(\d+(?:\.\d+)?)\s*m\b", raw)
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


def _wikitext(title: str, language: str) -> str:
    wiki = _client(language)
    params = wiki._construct_params_standalone({
        "action": "parse",
        "page": title,
        "prop": "wikitext",
    })
    try:
        body = wiki._get(wiki.language, params)
    except wikipediaapi.WikiRateLimitError as exc:
        raise _Busy(_BUSY) from exc
    except wikipediaapi.WikipediaException as exc:
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
    if isinstance(body, dict) and body.get("error"):
        info = body["error"].get("info") if isinstance(body["error"], dict) else "위키 오류"
        raise ValueError(str(info))
    parse = body.get("parse") if isinstance(body, dict) else None
    text = parse.get("wikitext") if isinstance(parse, dict) else None
    if isinstance(text, dict):
        text = text.get("*")
    if not isinstance(text, str):
        raise ValueError("위키 문서를 읽지 못했습니다")
    return text


class _Busy(ValueError):
    pass


def _language(language: str) -> str:
    text = (language or "en").lower()
    if not re.fullmatch(r"[a-z]{2,3}", text):
        raise ValueError("위키 언어가 아닙니다")
    return text


def _client(language: str = "en") -> wikipediaapi.Wikipedia:
    language = _language(language)
    wiki = _WIKIS.get(language)
    if wiki is None:
        wiki = wikipediaapi.Wikipedia(
            user_agent=os.environ.get(
                "HTTP_USER_AGENT",
                "glow-collect/0.1 (local actor collection)",
            ),
            language=language,
        )
        _WIKIS[language] = wiki
    return wiki


def _page(title: str, language: str) -> wikipediaapi.WikipediaPage | None:
    try:
        page = _client(language).page(title)
        exists = page.exists()
    except wikipediaapi.WikiRateLimitError as exc:
        raise _Busy(_BUSY) from exc
    except wikipediaapi.WikipediaException as exc:
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
    if not exists:
        return None
    return page
