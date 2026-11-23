import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://gmmtv.fandom.com"
SOURCE = "gmmtv_fandom"
_API = BASE_URL + "/api.php"

_PEOPLE = re.compile(r"\{\{People\b(.*?)\n\}\}", re.S)
_FIELD = re.compile(r"^[ \t]*\|([A-Za-z0-9_]+)[ \t]*=[ \t]*(.*)$", re.M)
_SECTION = re.compile(r"^==\s*Early Life\s*==\s*\n(.*?)(?=\n==|\Z)", re.S | re.M)
_REF = re.compile(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", re.S)


def search(query: str, limit: int = 4) -> list[dict]:
    titles = _opensearch(query)
    profiles = []
    for title in titles:
        if "/" in title:
            continue
        try:
            profile = fetch_page(title)
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        if profile is None:
            continue
        profiles.append(profile)
        if len(profiles) >= limit:
            break
    return profiles


def fetch_page(title: str) -> dict | None:
    page = _page_title(title)
    wikitext = _wikitext(page)
    people = _PEOPLE.search(wikitext)
    if people is None:
        return None
    fields = {key: value.strip() for key, value in _FIELD.findall(people.group(1))}
    socials = _socials(fields.get("social_media", ""))
    early = _early_life(wikitext)
    return {
        "title": page,
        "name": _plain(fields.get("title1")) or page,
        "url": f"{BASE_URL}/wiki/{urllib.parse.quote(page.replace(' ', '_'))}",
        "image_url": _image_url(fields.get("image1") or fields.get("image")),
        "birth_name": _plain(fields.get("birth_name")),
        "nickname": _plain(fields.get("nickname")),
        "native_name": _plain(fields.get("thai")),
        "birthday": _birthday(fields.get("birthday", "")),
        "birth_place": _plain(fields.get("birth_place")),
        "height": _measure(fields.get("height", ""), "cm"),
        "weight": _measure(fields.get("weight", ""), "kg"),
        "years_active": _plain(fields.get("years_active")),
        "socials": socials,
        "early_life": early,
    }


def selected_payload(profile: dict, fields: list[str]) -> dict:
    allowed = {
        "birth_name",
        "nickname",
        "native_name",
        "birthday",
        "birth_place",
        "height",
        "weight",
        "years_active",
        "socials",
        "early_life",
        "image",
    }
    chosen = [field for field in fields if field in allowed]
    if not chosen:
        raise ValueError("넣을 항목을 하나 이상 고르세요")
    payload: dict = {"url": profile["url"]}
    for key in (
        "birth_name",
        "nickname",
        "native_name",
        "birthday",
        "birth_place",
        "height",
        "weight",
        "years_active",
        "early_life",
    ):
        if key in chosen and profile.get(key):
            payload[key] = profile[key]
    if "socials" in chosen and profile["socials"]:
        payload["socials"] = profile["socials"]
    if "image" in chosen and profile.get("image_url"):
        payload["image_url"] = profile["image_url"]
    if len(payload) == 1:
        raise ValueError("고른 항목에 값이 없습니다")
    return payload


def _opensearch(query: str) -> list[str]:
    body = _api({"action": "opensearch", "search": query, "limit": 8, "format": "json"})
    if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
        return []
    return [title for title in body[1] if isinstance(title, str)]


def _wikitext(title: str) -> str:
    body = _api({"action": "parse", "page": title, "prop": "wikitext", "format": "json"})
    parse = body.get("parse") if isinstance(body, dict) else None
    if not isinstance(parse, dict):
        raise ValueError("위키 문서를 읽지 못했습니다")
    text = parse.get("wikitext")
    if isinstance(text, dict):
        text = text.get("*")
    if not isinstance(text, str):
        raise ValueError("위키 문서를 읽지 못했습니다")
    return text


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
    return _info_url(body)


def _file_name(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^\[\[(?:File|Image):", "", text, flags=re.I)
    text = text.split("|", 1)[0].split("]]", 1)[0].strip()
    text = re.sub(r"^(?:File|Image):", "", text, flags=re.I).strip()
    return text or None


def _info_url(body: dict | list) -> str | None:
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


def _early_life(wikitext: str) -> str | None:
    match = _SECTION.search(wikitext)
    if match is None:
        return None
    text = _REF.sub("", match.group(1))
    text = re.sub(r"\{\{[^{}]+\}\}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text == "{{Stub}}":
        return None
    return text


def _socials(raw: str) -> list[dict]:
    found = []
    seen: set[str] = set()
    patterns = (
        ("instagram", r"\{\{IG\|([^}|]+)"),
        ("x", r"\{\{X\|([^}|]+)"),
        ("threads", r"\{\{TD\|@?([^}|]+)"),
        ("tiktok", r"\{\{TT\|@?([^}|]+)"),
    )
    hosts = {
        "instagram": "https://www.instagram.com/",
        "x": "https://x.com/",
        "threads": "https://www.threads.net/@",
        "tiktok": "https://www.tiktok.com/@",
    }
    for kind, pattern in patterns:
        match = re.search(pattern, raw)
        if match is None:
            continue
        handle = match.group(1).strip().lstrip("@")
        url = hosts[kind] + handle
        if url in seen:
            continue
        seen.add(url)
        found.append({"kind": kind, "url": url})
    return found


def _birthday(raw: str) -> str | None:
    match = re.search(r"\{\{(?:age|Birth date)\|(\d{4})\|(\d{1,2})\|(\d{1,2})", raw)
    if match is None:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _measure(raw: str, unit: str) -> str | None:
    match = re.search(r"\{\{(?:Height|Weight)\|(\d+)", raw)
    if match is None:
        return None
    return f"{match.group(1)} {unit}"


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", value)
    text = re.sub(r"\{\{[^{}]+\}\}", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or None


def _page_title(title: str) -> str:
    text = " ".join((title or "").split())
    if not text or any(char in text for char in "|{}[]#<>"):
        raise ValueError("위키 문서 제목이 아닙니다")
    return text


def _api(params: dict) -> dict | list:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{_API}?{query}",
        headers={"User-Agent": os.environ.get("HTTP_USER_AGENT", "glow-collect/0.1")},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if isinstance(body, dict) and body.get("error"):
        info = body["error"].get("info") if isinstance(body["error"], dict) else "위키 오류"
        raise ValueError(str(info))
    return body
