import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://www.sapphiceffect.com"
SOURCE = "sapphic_effect"
_SLUGS: list[str] = []
_SLUGS_AT: datetime | None = None

_SHIP = re.compile(
    r'href":"(/ships/[^"]+)","name":"([^"]+)","avatarUrl":"([^"]+)"'
)
_COMPANY = re.compile(r'href":"(/companies/([^"]+))","name":"([^"]+)"')
_SOCIAL = re.compile(
    r'href":"(https://(?:www\.)?(?:instagram\.com|tiktok\.com|x\.com|twitter\.com)/[^"]+)"'
)
_BIRTHDAY = re.compile(r'"birthday":"(\d{4}-\d{2}-\d{2})')
_PROFILE_IMAGE = re.compile(
    r'https://pub-[^"\\]+/star-avatars/star-profile/[^"\\]+'
)


def search(query: str, limit: int = 8) -> list[dict]:
    slugs = _star_slugs()
    ranked = [(score, slug) for slug in slugs if (score := _score(query, slug)) > 0]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    profiles = []
    for _, slug in ranked[:limit]:
        try:
            profiles.append(fetch_star(slug))
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return profiles


def fetch_star(slug: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", slug or ""):
        raise ValueError("스타 slug가 아닙니다")
    html = _get(f"/stars/{slug}")
    text = html.replace('\\"', '"').replace("\\u0026", "&")
    title = re.search(r"<title>(.*?)</title>", html)
    name = title.group(1).split("—")[0].strip() if title else slug
    birthday = _BIRTHDAY.search(text)
    image = _PROFILE_IMAGE.search(text)
    company = _COMPANY.search(text)
    ships = _cards(text, _SHIP, "/ships/")
    socials = []
    seen_social: set[str] = set()
    for url in _SOCIAL.findall(text):
        if url in seen_social:
            continue
        seen_social.add(url)
        socials.append({"kind": _social_kind(url), "url": url})
    return {
        "slug": slug,
        "name": name or slug,
        "url": f"{BASE_URL}/stars/{slug}",
        "birthday": birthday.group(1) if birthday else None,
        "image_url": image.group(0) if image else None,
        "company": (
            {"name": company.group(3).strip(), "slug": company.group(2)}
            if company
            else None
        ),
        "ships": ships,
        "socials": socials,
        "biography": _biography(html),
    }


def selected_payload(profile: dict, fields: list[str]) -> dict:
    allowed = {"birthday", "image", "company", "ships", "socials", "biography"}
    chosen = [field for field in fields if field in allowed]
    if not chosen:
        raise ValueError("넣을 항목을 하나 이상 고르세요")
    payload: dict = {"url": profile["url"]}
    if "birthday" in chosen and profile["birthday"]:
        payload["birthday"] = profile["birthday"]
    if "image" in chosen and profile["image_url"]:
        payload["image_url"] = profile["image_url"]
    if "company" in chosen and profile["company"]:
        payload["company"] = profile["company"]
    if "socials" in chosen and profile["socials"]:
        payload["socials"] = profile["socials"]
    if "biography" in chosen and profile["biography"]:
        payload["biography"] = profile["biography"]
    if len(payload) == 1 and not ("ships" in chosen and profile.get("ships")):
        raise ValueError("고른 항목에 값이 없습니다")
    return payload


def _star_slugs() -> list[str]:
    global _SLUGS, _SLUGS_AT
    now = datetime.now(timezone.utc)
    if _SLUGS and _SLUGS_AT and now - _SLUGS_AT < timedelta(hours=6):
        return _SLUGS
    xml = _get("/sitemap.xml")
    slugs = []
    for loc in re.findall(r"<loc>(.*?)</loc>", xml):
        marker = "/stars/"
        if marker not in loc:
            continue
        slug = loc.split(marker, 1)[1].strip("/")
        if re.fullmatch(r"[a-z0-9-]+", slug):
            slugs.append(slug)
    _SLUGS = slugs
    _SLUGS_AT = now
    return slugs


def _score(query: str, slug: str) -> int:
    tokens = [token for token in re.split(r"[^a-z0-9]+", query.lower()) if len(token) >= 3]
    if not tokens:
        compact = re.sub(r"[^a-z0-9]+", "", query.lower())
        return 100 if compact and compact == slug else 0
    score = 0
    if slug in tokens:
        score += 50
    for token in tokens:
        if token == slug:
            score += 40
        elif token in slug:
            score += 15
    return score


def _get(path: str) -> str:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"User-Agent": os.environ.get("HTTP_USER_AGENT", "glow-collect/0.1")},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def _social_kind(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    if host.startswith("instagram."):
        return "instagram"
    if host.startswith("tiktok."):
        return "tiktok"
    if host in {"x.com", "twitter.com"}:
        return "x"
    return host


_BIO_HEADS = (
    "Biography \\u0026 Education",
    "Biography & Education",
    "Biography \\u0026 Career Path",
    "Biography & Career Path",
    "Biography \\u0026 Personal Life",
    "Biography & Personal Life",
    "Biography \\u0026 Acting Career",
)


def _biography(html: str) -> str | None:
    start = -1
    for head in _BIO_HEADS:
        start = html.find(head)
        if start >= 0:
            break
    if start < 0:
        return None
    end = re.search(r"\d+:\[", html[start:])
    if end is None:
        return None
    text = html[start : start + end.start()]
    text = (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\u0026", "&")
        .replace('\\"', '"')
        .replace("\\u0027", "'")
    )
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _cards(text: str, pattern: re.Pattern[str], prefix: str) -> list[dict]:
    cards = []
    seen: set[str] = set()
    for path, name, image_url in pattern.findall(text):
        slug = path.removeprefix(prefix)
        if slug in seen:
            continue
        seen.add(slug)
        cards.append({"name": _clean(name), "slug": slug, "image_url": image_url})
    return cards


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
