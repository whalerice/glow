import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import NamedTuple

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

import psycopg
from psycopg.types.json import Json

from app.agency import name_key
from app.ids import person_mdl_id, work_mdl_id
from app.tmdb import fill_person

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
KINDS = {"Drama": "drama", "Movie": "movie"}
CREDIT_ROLES = ("Screenwriter & Director", "Director", "Screenwriter")
_CREDIT_ROLE_CODES = {
    "Director": ("d",),
    "Screenwriter": ("w",),
    "Screenwriter & Director": ("d", "w"),
}
_BORN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
NETWORK_TYPE = "방송사"


class DramaDetail(NamedTuple):
    image_url: str | None
    synopsis: str | None
    native_title: str | None
    tags: list[str]
    networks: list[str]
    aired: str | None
    aired_on: str | None
    content_rating: str | None


class CollectResult(NamedTuple):
    mdl_id: str
    status: str
    person_id: int
    works: int = 0
    created: tuple = ()


def register(raw_id: str) -> CollectResult:
    mdl_id = person_mdl_id(raw_id)
    if mdl_id is None:
        raise ValueError("숫자 id가 아닙니다")

    with connect() as conn:
        apply_schema(conn)
        existing = conn.execute(
            "SELECT id, deleted FROM person WHERE mdl_id = %s",
            (mdl_id,),
        ).fetchone()
        if existing is not None and int(existing[1] or 0) != 0:
            conn.commit()
            return CollectResult(mdl_id, "collected", int(existing[0]), 0, ())
        person_id = mark_registered(conn, mdl_id)
        conn.commit()

    body, error = fetch_person(mdl_id)
    if body is not None and error is None:
        fill_filmography(body)
    posters = poster_map(body) if body is not None and error is None else {}
    with connect() as conn:
        if error is not None or body is None:
            mark_failed(conn, person_id, error or "success false")
            conn.commit()
            return CollectResult(mdl_id, "failed", person_id)
        try:
            link_count, created = save_success(conn, person_id, body, posters)
        except Exception as exc:
            conn.rollback()
            mark_failed(conn, person_id, str(exc))
            conn.commit()
            return CollectResult(mdl_id, "failed", person_id)
        conn.commit()
    try:
        fill_person(person_id)
    except Exception:
        pass
    return CollectResult(mdl_id, "collected", person_id, link_count, tuple(created))


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL이 없습니다")
    return psycopg.connect(url)


def apply_schema(conn: psycopg.Connection) -> None:
    kept = _drop_keyed_company_type(conn)
    _rename_type_tables(conn)
    script = SCHEMA_PATH.read_text()
    for statement in script.split(";"):
        sql = statement.strip()
        if sql:
            conn.execute(sql)
    if kept is not None:
        for company_id, name in kept:
            conn.execute(
                """
                INSERT INTO company_type (company_id, org_type_id)
                SELECT %s, id FROM org_type WHERE name = %s
                ON CONFLICT DO NOTHING
                """,
                (company_id, name),
            )
    _rewrite_aired(conn)
    _rewrite_ratings(conn)
    _rewrite_company_keys(conn)
    _fill_person_roles(conn)
    _normalize_born_texts(conn)
    _migrate_work_status(conn)


def _drop_keyed_company_type(conn: psycopg.Connection) -> list[tuple] | None:
    old = conn.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'company_type' AND column_name = 'key'
        """
    ).fetchone()
    if old is None:
        return None
    kept = conn.execute(
        """
        SELECT l.company_id, t.key
        FROM company_type_link l
        JOIN company_type t ON t.key = l.type_key
        """
    ).fetchall()
    conn.execute("DROP TABLE company_type_link")
    conn.execute("DROP TABLE company_type")
    return [(int(company_id), name) for company_id, name in kept]


def _rename_type_tables(conn: psycopg.Connection) -> None:
    old = conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'company_type_link'
        """
    ).fetchone()
    if old is None:
        return
    conn.execute("ALTER TABLE company_type RENAME TO org_type")
    conn.execute("ALTER TABLE company_type_link RENAME TO company_type")
    conn.execute("ALTER TABLE company_type RENAME COLUMN company_type_id TO org_type_id")


def grant_person_roles(conn: psycopg.Connection, person_id: int, codes: tuple[str, ...]) -> None:
    for code in codes:
        conn.execute(
            """
            INSERT INTO person_role (person_id, role_code)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (person_id, code),
        )


def credit_role_codes(role: str) -> tuple[str, ...]:
    return _CREDIT_ROLE_CODES.get(role, ())


def normalize_born(value: object) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", re.sub(r"\s+", " ", text))
    if match is None:
        return text
    month = _BORN_MONTHS.get(match.group(1).casefold())
    if month is None:
        return text
    try:
        return date(int(match.group(3)), month, int(match.group(2))).isoformat()
    except ValueError:
        return text


def _fill_person_roles(conn: psycopg.Connection) -> None:
    has_listed = conn.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'person' AND column_name = 'listed'
        """
    ).fetchone()
    if has_listed:
        conn.execute(
            """
            INSERT INTO person_role (person_id, role_code)
            SELECT id, 'a' FROM person WHERE listed
            ON CONFLICT DO NOTHING
            """
        )
        conn.execute("ALTER TABLE person DROP COLUMN listed")
    conn.execute(
        """
        INSERT INTO person_role (person_id, role_code)
        SELECT DISTINCT person_id, 'd'
        FROM person_work
        WHERE role IN ('Director', 'Screenwriter & Director')
        ON CONFLICT DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO person_role (person_id, role_code)
        SELECT DISTINCT person_id, 'w'
        FROM person_work
        WHERE role IN ('Screenwriter', 'Screenwriter & Director')
        ON CONFLICT DO NOTHING
        """
    )


def _migrate_work_status(conn: psycopg.Connection) -> None:
    old = conn.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'work'
          AND column_name = 'tmdb_status'
        """
    ).fetchone()
    if old is not None:
        conn.execute(
            """
            INSERT INTO work_status (key, name)
            SELECT DISTINCT btrim(tmdb_status), btrim(tmdb_status)
            FROM work
            WHERE tmdb_status IS NOT NULL AND btrim(tmdb_status) <> ''
            ON CONFLICT (key) DO NOTHING
            """
        )
        conn.execute(
            """
            UPDATE work
            SET status = NULLIF(btrim(tmdb_status), '')
            WHERE status IS NULL
            """
        )
        conn.execute("ALTER TABLE work DROP COLUMN tmdb_status")
    fk = conn.execute(
        """
        SELECT 1 FROM pg_constraint
        WHERE conname = 'work_status_fkey'
        """
    ).fetchone()
    if fk is None:
        conn.execute(
            """
            ALTER TABLE work
            ADD CONSTRAINT work_status_fkey
            FOREIGN KEY (status) REFERENCES work_status (key)
            """
        )


def _normalize_born_texts(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id, born_text FROM person WHERE born_text IS NOT NULL"
    ).fetchall()
    for person_id, raw in rows:
        parsed = normalize_born(raw)
        if parsed != raw:
            conn.execute(
                "UPDATE person SET born_text = %s WHERE id = %s",
                (parsed, person_id),
            )


def mark_registered(conn: psycopg.Connection, mdl_id: str) -> int:
    row = conn.execute(
        """
        INSERT INTO person (mdl_id, collect_status)
        VALUES (%s, 'registered')
        ON CONFLICT (mdl_id) DO UPDATE
        SET collect_status = 'registered',
            collect_error = NULL
        RETURNING id
        """,
        (mdl_id,),
    ).fetchone()
    person_id = int(row[0])
    grant_person_roles(conn, person_id, ("a",))
    return person_id


def mark_failed(conn: psycopg.Connection, person_id: int, error: str) -> None:
    conn.execute(
        """
        UPDATE person
        SET collect_status = 'failed',
            collect_error = %s
        WHERE id = %s
        """,
        (error[:500], person_id),
    )


def fetch_person(mdl_id: str) -> tuple[dict | None, str | None]:
    base = os.environ.get("KURYANA_BASE_URL", "https://kuryana.tbdh.app").rstrip("/")
    request = urllib.request.Request(
        f"{base}/v2/people/{mdl_id}",
        headers={"User-Agent": "glow-collect/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.load(response)
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        message = raw[:500]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("message"):
                message = str(parsed["message"])[:500]
        except json.JSONDecodeError:
            pass
        return None, f"{exc.code} {message}"
    except urllib.error.URLError as exc:
        return None, f"0 {exc.reason}"

    if status != 200 or not isinstance(body, dict) or body.get("success") is not True:
        message = ""
        if isinstance(body, dict) and body.get("message"):
            message = str(body["message"])
        return None, f"{status} {message or 'success false'}"
    return body, None


_FILM_KINDS = ("Drama", "Movie")


def fill_filmography(body: dict) -> None:
    data = body.get("data")
    if not isinstance(data, dict):
        return
    parsed = fetch_person_filmography(text_or_none(body.get("link")))
    if not parsed:
        return
    current = data.get("works") if isinstance(data.get("works"), dict) else {}
    known: dict[str, dict] = {}
    for items in current.values():
        if not isinstance(items, list):
            continue
        for item in items:
            slug = item.get("slug") if isinstance(item, dict) else None
            if isinstance(slug, str):
                known[slug] = item
    works: dict[str, list] = {}
    for kind in _FILM_KINDS:
        merged = []
        for item in parsed.get(kind, []):
            old = known.get(item["slug"])
            if old is not None:
                if item.get("episodes") is None and isinstance(old.get("episodes"), int):
                    item["episodes"] = old["episodes"]
                if item.get("rating") is None and isinstance(old.get("rating"), (int, float)):
                    item["rating"] = old["rating"]
            merged.append(item)
        works[kind] = merged
    data["works"] = works


_SOCIAL_LABELS = {
    "instagram": "instagram",
    "twitter": "x",
    "x": "x",
    "tiktok": "tiktok",
    "facebook": "facebook",
    "youtube": "youtube",
    "weibo": "weibo",
    "threads": "threads",
}


def fetch_person_socials(link: str | None) -> list[dict]:
    if not link or "/people/" not in link:
        return []
    try:
        response = cffi_requests.get(link, impersonate="chrome110", timeout=20)
    except Exception:
        return []
    if response.status_code != 200:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    found = []
    seen: set[str] = set()
    for header in soup.select("div.box-header"):
        if header.get_text(strip=True) != "Details":
            continue
        box = header.find_parent("div", class_="box")
        if box is None:
            continue
        for item in box.select("li.list-item"):
            label_node = item.find("b")
            if label_node is None:
                continue
            kind = _SOCIAL_LABELS.get(label_node.get_text(strip=True).rstrip(":").casefold())
            if kind is None:
                continue
            anchor = item.find("a", href=True)
            url = anchor["href"].strip() if anchor else ""
            if not url.startswith("http"):
                handle = item.get_text(" ", strip=True).split(":", 1)[-1].strip().lstrip("@")
                if not handle:
                    continue
                url = _social_url(kind, handle)
            if url in seen:
                continue
            seen.add(url)
            found.append({"kind": kind, "url": url})
    return found


def _social_url(kind: str, handle: str) -> str:
    bases = {
        "instagram": "https://www.instagram.com/",
        "x": "https://x.com/",
        "tiktok": "https://www.tiktok.com/@",
        "facebook": "https://www.facebook.com/",
        "youtube": "https://www.youtube.com/@",
        "weibo": "https://weibo.com/",
        "threads": "https://www.threads.net/@",
    }
    return bases.get(kind, "") + handle


def fetch_person_filmography(link: str | None) -> dict[str, list[dict]] | None:
    if not link or "/people/" not in link:
        return None
    try:
        response = cffi_requests.get(link, impersonate="chrome110", timeout=20)
    except Exception:
        return None
    if response.status_code != 200 or "film-title" not in response.text:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    found = {kind: [] for kind in _FILM_KINDS}
    seen = {kind: set() for kind in _FILM_KINDS}
    for header in soup.select("div.box-body > h5.header"):
        kind = header.get_text(strip=True)
        if kind not in found:
            continue
        table = header.find_next_sibling("table", class_="film-list")
        if table is None:
            continue
        for row in table.select("tbody > tr"):
            item = _film_row(row)
            if item is None or item["slug"] in seen[kind]:
                continue
            seen[kind].add(item["slug"])
            found[kind].append(item)
    if not any(found.values()):
        return None
    return found


def _film_row(row) -> dict | None:
    cell = row.select_one("td.title")
    link = cell.select_one("b a[href]") if cell else None
    if link is None and cell is not None:
        for anchor in cell.select("a[href]"):
            if anchor.get_text(strip=True):
                link = anchor
                break
    if link is None:
        return None
    title = link.get_text(strip=True) or (link.get("title") or "").strip()
    slug = (link.get("href") or "").split("?", 1)[0].strip("/")
    if not title or re.fullmatch(r"\d+-.+", slug) is None:
        return None
    year_el = row.select_one("td.year")
    year_text = year_el.get_text(strip=True) if year_el else ""
    year = int(year_text) if year_text.isdigit() else None
    role_el = row.select_one("td.role > div.text-muted")
    char_el = row.select_one("td.role > div.name")
    rating_el = row.select_one("td.text-center > div.text-sm")
    rating = None
    if rating_el:
        try:
            rating = float(rating_el.get_text(strip=True))
        except ValueError:
            rating = None
    character = char_el.get_text(strip=True) if char_el else ""
    return {
        "title": title,
        "slug": slug,
        "link": f"https://mydramalist.com/{slug}",
        "year": year,
        "episodes": None,
        "rating": rating,
        "role": role_el.get_text(strip=True) if role_el else "",
        "character": character or None,
    }


def poster_map(body: dict) -> dict[str, DramaDetail | None]:
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    works = data.get("works") if isinstance(data.get("works"), dict) else {}
    slugs: list[str] = []
    seen: set[str] = set()
    for source_kind, items in works.items():
        if source_kind not in KINDS or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if isinstance(slug, str) and slug not in seen:
                seen.add(slug)
                slugs.append(slug)
    return {slug: fetch_drama_text(slug) for slug in slugs}


def fetch_drama_text(slug: str) -> DramaDetail | None:
    data = load_drama(slug)
    if data is None:
        return None
    return drama_detail(data)


def load_drama(slug: str) -> dict | None:
    base = os.environ.get("KURYANA_BASE_URL", "https://kuryana.tbdh.app").rstrip("/")
    request = urllib.request.Request(
        f"{base}/v2/dramas/{urllib.parse.quote(slug)}",
        headers={"User-Agent": "glow-collect/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def queer_id(conn: psycopg.Connection, tags: list[str]) -> int | None:
    gl = any("lesbian" in tag.casefold() for tag in tags)
    bl = "Gay Romance" in tags or "Gay Male Lead" in tags
    name = "LGBTQ" if gl and bl else "GL" if gl else "BL" if bl else None
    if name is None:
        return None
    row = conn.execute("SELECT id FROM queer WHERE name = %s", (name,)).fetchone()
    return int(row[0]) if row else None


def drama_detail(data: dict) -> DramaDetail:
    raw_tags = data.get("tags")
    if not isinstance(raw_tags, list):
        raw_tags = []
    return DramaDetail(
        text_or_none(data.get("poster")),
        text_or_none(data.get("synopsis")),
        text_or_none(data.get("native_title")),
        [item.strip() for item in raw_tags if isinstance(item, str) and item.strip()],
        network_names(data.get("original_network")),
        aired_span(data.get("aired")),
        detail_text(data.get("aired_on")),
        content_code(data.get("content_rating")),
    )


def mdl_slug(mdl_id: str) -> str | None:
    try:
        response = cffi_requests.get(
            "https://mydramalist.com/search",
            params={"q": mdl_id},
            impersonate="chrome110",
            timeout=20,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    prefix = f"/{mdl_id}-"
    for anchor in BeautifulSoup(response.text, "html.parser").select("a[href]"):
        href = (anchor.get("href") or "").split("?", 1)[0]
        if href.startswith(prefix):
            return href.strip("/")
    return None


def register_work(raw_id: str) -> tuple[int, str, bool]:
    mdl_id = person_mdl_id(raw_id)
    if mdl_id is None:
        raise ValueError("숫자 id가 아닙니다")
    with connect() as conn:
        apply_schema(conn)
        found = conn.execute("SELECT id FROM work WHERE mdl_id = %s", (mdl_id,)).fetchone()
        if found:
            conn.commit()
            return int(found[0]), mdl_id, True
        conn.commit()
    return _collect_work(mdl_id), mdl_id, False


def refresh_work(work_id: int) -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT title, mdl_id, deleted FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
    if row is None or int(row[2] or 0) != 0:
        return ""
    title, mdl_id, _deleted = row
    name = title if isinstance(title, str) else ""
    if isinstance(mdl_id, str) and mdl_id.strip():
        _collect_work(mdl_id.strip(), cast=False)
    try:
        from app.tmdb import recollect

        recollect(work_id)
    except Exception:
        pass
    return name


def _collect_work(mdl_id: str, cast: bool = True) -> int:
    slug = mdl_id
    data = load_drama(slug)
    if data is None:
        slug = mdl_slug(mdl_id) or ""
        data = load_drama(slug) if slug else None
    if data is None:
        raise ValueError("작품을 찾지 못했습니다")
    kind = work_kind(data.get("type"))
    item = {
        "title": data.get("title"),
        "year": data.get("year"),
        "episodes": data.get("episodes"),
        "rating": data.get("rating"),
        "link": f"https://mydramalist.com/{slug}",
        "slug": slug,
    }
    with connect() as conn:
        work_id, _created = upsert_work(conn, item, kind, drama_detail(data))
        if work_id is None:
            raise ValueError("제목이 없습니다")
        conn.commit()
    if kind != "movie":
        try:
            collect_episodes(work_id)
        except Exception:
            pass
    if cast:
        for item in main_cast(slug):
            if is_male(item["mdl_id"]):
                continue
            try:
                result = register(item["mdl_id"])
            except Exception:
                continue
            link_main_role(work_id, result.person_id, item["character"])
    else:
        save_missing_main_roles(work_id, slug)
    try:
        save_where_to_watch(work_id, slug)
    except Exception:
        pass
    return work_id


def work_kind(value: object) -> str:
    if value == "Movie":
        return "movie"
    if value == "Drama":
        return "drama"
    if isinstance(value, str) and value.strip():
        return "tv_show"
    raise ValueError("종류가 없습니다")


def detail_text(value: object) -> str | None:
    if isinstance(value, list):
        parts = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return ", ".join(parts) or None
    return text_or_none(value)


_RATING = re.compile(r"^(\d+\+)")


def content_code(value: object) -> str | None:
    text = detail_text(value)
    if text is None:
        return None
    text = text.strip()
    if text == "G - All Ages":
        return "전체관람가"
    match = _RATING.match(text)
    if match is None:
        return text
    return match.group(1)


_AIR_DAY = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
_AIR_RANGE = re.compile(r"^(.+?)\s+-\s+(.+)$")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def aired_span(value: object) -> str | None:
    text = detail_text(value)
    if text is None:
        return None
    match = _AIR_RANGE.match(text.strip())
    if match is None:
        return text
    start = _iso_day(match.group(1))
    end = _iso_day(match.group(2))
    if start is None or end is None:
        return text
    return f"{start} ~ {end}"


def _iso_day(text: str) -> str | None:
    match = _AIR_DAY.match(text.strip())
    if match is None:
        return None
    month = _MONTHS.get(match.group(1).casefold()[:3])
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(2))).isoformat()
    except ValueError:
        return None


def _rewrite_company_keys(conn: psycopg.Connection) -> None:
    rows = conn.execute("SELECT id, name, name_key FROM company").fetchall()
    for company_id, name, current in rows:
        key = name_key(name)
        if key and key != current:
            conn.execute(
                "UPDATE company SET name_key = %s WHERE id = %s",
                (key, company_id),
            )


def _rewrite_aired(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id, aired FROM work WHERE aired IS NOT NULL AND aired !~ '^[0-9]{4}-'"
    ).fetchall()
    for work_id, aired in rows:
        formatted = aired_span(aired)
        if formatted != aired:
            conn.execute(
                "UPDATE work SET aired = %s WHERE id = %s",
                (formatted, work_id),
            )


def _rewrite_ratings(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id, content_rating FROM work WHERE content_rating ~ '^[0-9]+\\+.' OR content_rating = 'G - All Ages'"
    ).fetchall()
    for work_id, rating in rows:
        formatted = content_code(rating)
        if formatted != rating:
            conn.execute(
                "UPDATE work SET content_rating = %s WHERE id = %s",
                (formatted, work_id),
            )


def network_names(value: object) -> list[str]:
    raw = value if isinstance(value, list) else []
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        key = name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def save_broadcasters(conn: psycopg.Connection, work_id: int, names: list[str]) -> None:
    # ponytail: work_company is broadcast links only. Delete-all breaks once production links exist.
    conn.execute("DELETE FROM work_company WHERE work_id = %s", (work_id,))
    for name in names:
        company_id = _upsert_company_name(conn, name)
        conn.execute(
            """
            INSERT INTO company_type (company_id, org_type_id)
            SELECT %s, id FROM org_type WHERE name = %s
            ON CONFLICT DO NOTHING
            """,
            (company_id, NETWORK_TYPE),
        )
        conn.execute(
            """
            INSERT INTO work_company (work_id, company_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (work_id, company_id),
        )
    conn.execute("UPDATE work SET networks_at = now() WHERE id = %s", (work_id,))


def save_air(conn: psycopg.Connection, work_id: int, detail: DramaDetail) -> None:
    conn.execute(
        """
        UPDATE work
        SET aired = %s,
            aired_on = %s,
            content_rating = %s,
            air_at = now()
        WHERE id = %s
        """,
        (detail.aired, detail.aired_on, detail.content_rating, work_id),
    )


def _upsert_company_name(conn: psycopg.Connection, name: str) -> int:
    key = name_key(name)
    row = conn.execute(
        "SELECT id FROM company WHERE name_key = %s ORDER BY id",
        (key,),
    ).fetchone()
    if row:
        return int(row[0])
    created = conn.execute(
        """
        INSERT INTO company (name, name_key)
        VALUES (%s, %s)
        RETURNING id
        """,
        (name, key),
    ).fetchone()
    return int(created[0])


def save_drama_detail(work_id: int) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT mdl_url, detail_at, networks_at, air_at FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
    if row is None:
        return
    mdl_url, detail_at, networks_at, air_at = row
    slug = drama_slug(mdl_url)
    if slug is None:
        return
    if detail_at is not None and networks_at is not None and air_at is not None:
        return
    detail = fetch_drama_text(slug)
    if detail is None:
        return
    with connect() as conn:
        conn.execute(
            """
            UPDATE work
            SET synopsis = COALESCE(%s, synopsis),
                native_title = COALESCE(%s, native_title),
                tags = %s::text[],
                queer = %s,
                image_url = COALESCE(%s, image_url),
                detail_at = now()
            WHERE id = %s AND detail_at IS NULL
            """,
            (
                detail.synopsis,
                detail.native_title,
                detail.tags,
                queer_id(conn, detail.tags),
                detail.image_url,
                work_id,
            ),
        )
        save_broadcasters(conn, work_id, detail.networks)
        save_air(conn, work_id, detail)
        conn.commit()


def fill_drama_details() -> None:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, mdl_url, detail_at, networks_at, air_at FROM work
            WHERE mdl_url IS NOT NULL
              AND (detail_at IS NULL OR networks_at IS NULL OR air_at IS NULL)
            """
        ).fetchall()
    for work_id, mdl_url, detail_at, networks_at, air_at in rows:
        slug = drama_slug(mdl_url)
        if slug is None:
            continue
        if detail_at is not None and networks_at is not None and air_at is not None:
            continue
        try:
            detail = fetch_drama_text(slug)
        except Exception:
            detail = None
        if detail is None:
            continue
        with connect() as conn:
            conn.execute(
                """
                UPDATE work
                SET synopsis = COALESCE(%s, synopsis),
                    native_title = COALESCE(%s, native_title),
                    tags = %s::text[],
                    queer = %s,
                    image_url = COALESCE(%s, image_url),
                    detail_at = now()
                WHERE id = %s AND detail_at IS NULL
                """,
                (
                    detail.synopsis,
                    detail.native_title,
                    detail.tags,
                    queer_id(conn, detail.tags),
                    detail.image_url,
                    work_id,
                ),
            )
            save_broadcasters(conn, work_id, detail.networks)
            save_air(conn, work_id, detail)
            conn.commit()


def save_success(
    conn: psycopg.Connection,
    person_id: int,
    body: dict,
    posters: dict[str, DramaDetail | None],
) -> int:
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    aliases = data.get("also_known_as")
    if not isinstance(aliases, list):
        aliases = []
    alias_list = [item for item in aliases if isinstance(item, str)]
    given, stage = given_and_stage(
        data.get("name"),
        data.get("first_name"),
        data.get("family_name"),
    )

    conn.execute(
        """
        UPDATE person
        SET name = %s,
            native_name = %s,
            first_name = %s,
            family_name = %s,
            stage_name = %s,
            also_known_as = %s,
            nationality = %s,
            gender = %s,
            born_text = %s,
            image_url = %s,
            about = NULL,
            mdl_url = %s,
            collect_status = 'collected',
            collect_error = NULL,
            collected_at = now()
        WHERE id = %s
        """,
        (
            text_or_none(data.get("name")),
            text_or_none(data.get("native_name")),
            given,
            text_or_none(data.get("family_name")),
            stage,
            alias_list,
            text_or_none(data.get("nationality")),
            text_or_none(data.get("gender")),
            normalize_born(data.get("born")),
            text_or_none(data.get("image")),
            text_or_none(body.get("link")),
            person_id,
        ),
    )

    links: dict[tuple[int, str], str | None] = {}
    created: list[dict] = []
    seen: set[int] = set()
    works = data.get("works") if isinstance(data.get("works"), dict) else {}
    for source_kind, items in works.items():
        kind = KINDS.get(source_kind)
        if kind is None or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            work_id, is_new = upsert_work(conn, item, kind, posters.get(item.get("slug")))
            if work_id is None:
                continue
            if is_new and work_id not in seen:
                seen.add(work_id)
                created.append({"id": work_id, "title": text_or_none(item.get("title")) or ""})
            role = item.get("role")
            role_text = role if isinstance(role, str) else ""
            character = item.get("character")
            links[(work_id, role_text)] = character if isinstance(character, str) else None

    conn.execute("DELETE FROM person_work WHERE person_id = %s", (person_id,))
    for (work_id, role), character in links.items():
        conn.execute(
            """
            INSERT INTO person_work (person_id, work_id, role, character_name)
            VALUES (%s, %s, %s, %s)
            """,
            (person_id, work_id, role, character),
        )
    return len(links), created


def upsert_work(
    conn: psycopg.Connection,
    item: dict,
    kind: str,
    detail: DramaDetail | None,
) -> tuple[int | None, bool]:
    title = text_or_none(item.get("title"))
    if title is None:
        return None, False
    year = item.get("year") if isinstance(item.get("year"), int) else None
    episodes = item.get("episodes") if isinstance(item.get("episodes"), int) else None
    rating = item.get("rating") if isinstance(item.get("rating"), (int, float)) else None
    mdl_url = text_or_none(item.get("link"))
    mdl_id = work_mdl_id(item.get("slug"))
    image_url = detail.image_url if detail else None
    synopsis = detail.synopsis if detail else None
    native_title = detail.native_title if detail else None
    tags = detail.tags if detail else []
    pair = queer_id(conn, tags) if detail else None
    fetched = detail is not None

    if mdl_id:
        existing = conn.execute(
            "SELECT id, deleted FROM work WHERE mdl_id = %s",
            (mdl_id,),
        ).fetchone()
        if existing is not None and int(existing[1] or 0) != 0:
            return int(existing[0]), False
        row = conn.execute(
            """
            INSERT INTO work (
                mdl_id, title, kind, year, episodes, rating, mdl_url, image_url,
                synopsis, native_title, tags, queer, detail_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::text[], %s, CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT (mdl_id) DO UPDATE
            SET title = EXCLUDED.title,
                kind = EXCLUDED.kind,
                year = EXCLUDED.year,
                episodes = COALESCE(EXCLUDED.episodes, work.episodes),
                rating = EXCLUDED.rating,
                mdl_url = EXCLUDED.mdl_url,
                image_url = COALESCE(EXCLUDED.image_url, work.image_url),
                synopsis = COALESCE(EXCLUDED.synopsis, work.synopsis),
                native_title = COALESCE(EXCLUDED.native_title, work.native_title),
                tags = CASE WHEN %s THEN EXCLUDED.tags ELSE work.tags END,
                queer = CASE WHEN %s THEN EXCLUDED.queer ELSE work.queer END,
                detail_at = CASE WHEN %s THEN now() ELSE work.detail_at END
            WHERE work.deleted = 0
            RETURNING id, (xmax = 0)
            """,
            (
                mdl_id, title, kind, year, episodes, rating, mdl_url, image_url,
                synopsis, native_title, tags, pair, fetched, fetched, fetched, fetched,
            ),
        ).fetchone()
        if row is None:
            kept = conn.execute(
                "SELECT id FROM work WHERE mdl_id = %s",
                (mdl_id,),
            ).fetchone()
            return int(kept[0]), False
        return _store_broadcasters(conn, int(row[0]), detail), bool(row[1])

    row = conn.execute(
        """
        SELECT id, deleted FROM work
        WHERE mdl_id IS NULL
          AND title = %s
          AND year IS NOT DISTINCT FROM %s
          AND kind = %s
        """,
        (title, year, kind),
    ).fetchone()
    if row:
        if int(row[1] or 0) != 0:
            return int(row[0]), False
        conn.execute(
            """
            UPDATE work
            SET episodes = COALESCE(%s, episodes),
                rating = %s,
                mdl_url = %s,
                image_url = COALESCE(%s, image_url),
                synopsis = COALESCE(%s, synopsis),
                native_title = COALESCE(%s, native_title),
                tags = CASE WHEN %s THEN %s::text[] ELSE tags END,
                queer = CASE WHEN %s THEN %s ELSE queer END,
                detail_at = CASE WHEN %s THEN now() ELSE detail_at END
            WHERE id = %s AND deleted = 0
            """,
            (
                episodes, rating, mdl_url, image_url, synopsis, native_title,
                fetched, tags or [], fetched, pair, fetched, row[0],
            ),
        )
        return _store_broadcasters(conn, int(row[0]), detail), False
    row = conn.execute(
        """
        INSERT INTO work (
            title, kind, year, episodes, rating, mdl_url, image_url,
            synopsis, native_title, tags, queer, detail_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::text[], %s, CASE WHEN %s THEN now() ELSE NULL END)
        RETURNING id
        """,
        (
            title, kind, year, episodes, rating, mdl_url, image_url,
            synopsis, native_title, tags, pair, fetched,
        ),
    ).fetchone()
    return _store_broadcasters(conn, int(row[0]), detail), True


def _store_broadcasters(
    conn: psycopg.Connection,
    work_id: int,
    detail: DramaDetail | None,
) -> int:
    if detail is not None:
        save_broadcasters(conn, work_id, detail.networks)
        save_air(conn, work_id, detail)
    return work_id


def _stage_before(full: str | None, given: str | None) -> str | None:
    if full is None or given is None:
        return None
    match = re.search(rf"(?:^|\s){re.escape(given)}(?:\s|$)", full)
    if match is None or match.start() == 0:
        return None
    return full[: match.start()].strip() or None


def _before_suffix(full: str, suffix: str) -> str | None:
    match = re.search(rf"(?:^|\s){re.escape(suffix)}$", full)
    if match is None:
        return None
    return full[: match.start()].strip()


def given_and_stage(
    name: object,
    first_name: object,
    family_name: object,
) -> tuple[str | None, str | None]:
    full = text_or_none(name)
    given = text_or_none(first_name)
    family = text_or_none(family_name)
    if full is None or family is None:
        return given, _stage_before(full, given)
    head = _before_suffix(full, family)
    if head is None:
        return given, _stage_before(full, given)
    if not head:
        return given, None
    if given is not None and (head == given or _before_suffix(head, given) is not None):
        prefix = "" if head == given else _before_suffix(head, given)
        return given, prefix or None
    parts = head.split()
    if len(parts) == 1:
        return head, None
    return " ".join(parts[1:]), parts[0]


def _biography(value: object) -> str | None:
    text = text_or_none(value)
    if text and text.casefold() == "add biography":
        return None
    return text


def text_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _watch_offer(text: str) -> str | None:
    head = text.strip().casefold()
    if head.startswith("subscription"):
        return "유료 구독"
    if head.startswith("free"):
        return "무료"
    return None


def _split_watch(name: str, offer: str) -> tuple[str, str] | None:
    label = name.strip()
    extra = offer.strip()
    if extra:
        label = f"{label} {extra}"
    match = re.search(r"\b(subscription|free)\b", label, re.I)
    if match is None:
        return None
    provider = label[: match.start()].strip(" -")
    mapped = _watch_offer(label[match.start() :])
    if not provider or mapped is None:
        return None
    return provider, mapped


def where_to_watch(slug: str) -> list[tuple[str, str, str | None]] | None:
    try:
        response = cffi_requests.get(
            f"https://mydramalist.com/{slug}",
            impersonate="chrome110",
            timeout=20,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    box = None
    for header in soup.select("h3"):
        if header.get_text(strip=True).startswith("Where to Watch"):
            box = header.find_parent("div", class_="box")
            break
    if box is None:
        return []
    rows: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for col in box.select("div.box-body div.col-xs-12.col-lg-4"):
        link = col.select_one("a.text-primary")
        if link is None:
            continue
        name = link.get_text(strip=True)
        offer = ""
        for node in col.select("div.p-l > div"):
            text = node.get_text(" ", strip=True)
            if text and text != name:
                offer = text
                break
        if not name or not offer:
            continue
        key = (name, offer)
        if key in seen:
            continue
        seen.add(key)
        rows.append((name, offer, _watch_url(link.get("href"))))
    return rows


def _watch_url(href: object) -> str | None:
    if not isinstance(href, str) or "q=" not in href:
        return None
    query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("q", [""])[0]
    target = urllib.parse.unquote(query)
    if not target.startswith(("http://", "https://")):
        return None
    return target


def save_where_to_watch(work_id: int, slug: str) -> None:
    found = where_to_watch(slug)
    if found is None:
        return
    rows: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for name, offer, url in found:
        split = _split_watch(name, offer)
        if split is None:
            continue
        provider, mapped = split
        if (provider, mapped) in seen:
            continue
        seen.add((provider, mapped))
        rows.append((provider, mapped, url))
    with connect() as conn:
        conn.execute(
            "DELETE FROM work_provider WHERE work_id = %s AND country = %s",
            (work_id, ""),
        )
        for name, offer, url in rows:
            conn.execute(
                """
                INSERT INTO work_provider (work_id, country, name, offer, url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (work_id, "", name, offer, url),
            )
        from app.tmdb import _save_provider_companies

        _save_provider_companies(
            conn,
            [("", name, offer, url, None) for name, offer, url in rows],
        )
        conn.execute("DELETE FROM work_watch WHERE work_id = %s", (work_id,))
        conn.commit()


def drama_slug(mdl_url: str | None) -> str | None:
    if not mdl_url:
        return None
    path = urllib.parse.urlparse(mdl_url).path.strip("/")
    slug = path.split("/")[-1] if path else ""
    if not slug or slug.isdigit():
        return None
    return slug


def collect_episodes(work_id: int) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT mdl_url FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
    if row is None:
        raise ValueError("없는 작품입니다")
    slug = drama_slug(row[0])
    if slug is None:
        raise ValueError("에피소드 주소에 쓸 slug가 없습니다")
    episodes = fetch_episodes(slug)
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM work WHERE id = %s", (work_id,)).fetchone()
        if exists is None:
            raise ValueError("없는 작품입니다")
        conn.execute("DELETE FROM episode WHERE work_id = %s", (work_id,))
        for item in episodes:
            conn.execute(
                """
                INSERT INTO episode
                    (work_id, number, title, air_date, rating, votes, image_url, mdl_url, summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    work_id,
                    item["number"],
                    item["title"],
                    item["air_date"],
                    item["rating"],
                    item["votes"],
                    item["image_url"],
                    item["mdl_url"],
                    item["summary"],
                ),
            )
        if episodes:
            conn.execute(
                """
                UPDATE work
                SET episodes = %s
                WHERE id = %s AND (episodes IS NULL OR episodes = 0)
                """,
                (len(episodes), work_id),
            )
        conn.commit()
    return len(episodes)


def fetch_episodes(slug: str) -> list[dict]:
    base = os.environ.get("KURYANA_BASE_URL", "https://kuryana.tbdh.app").rstrip("/")
    request = urllib.request.Request(
        f"{base}/v2/dramas/{urllib.parse.quote(slug)}/episodes",
        headers={"User-Agent": "glow-collect/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError("에피소드를 읽지 못했습니다") from exc
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise ValueError("에피소드를 읽지 못했습니다") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("에피소드를 읽지 못했습니다")
    data = payload.get("data")
    raw = data.get("episodes") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise ValueError("에피소드 목록이 없습니다")
    episodes = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("number"), int):
            continue
        number = item["number"]
        if number in seen:
            continue
        seen.add(number)
        rating = item.get("rating")
        votes = item.get("votes")
        episodes.append(
            {
                "number": number,
                "title": text_or_none(item.get("title")),
                "air_date": text_or_none(item.get("air_date")),
                "rating": rating if isinstance(rating, (int, float)) else None,
                "votes": votes if isinstance(votes, int) else None,
                "image_url": text_or_none(item.get("image")),
                "mdl_url": text_or_none(item.get("link")),
                "summary": text_or_none(item.get("summary")),
            }
        )
    episodes.sort(key=lambda item: item["number"])
    return episodes


def collect_credits(work_id: int) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT mdl_url FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
    if row is None:
        raise ValueError("없는 작품입니다")
    slug = drama_slug(row[0])
    if slug is None:
        raise ValueError("작가·감독 주소에 쓸 slug가 없습니다")
    credits = fetch_credits(slug)
    profiles: dict[str, dict | None] = {}
    for mdl_id in dict.fromkeys(item["mdl_id"] for item in credits):
        body, _error = fetch_person(mdl_id)
        profiles[mdl_id] = body
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM work WHERE id = %s", (work_id,)).fetchone()
        if exists is None:
            raise ValueError("없는 작품입니다")
        conn.execute(
            "DELETE FROM person_work WHERE work_id = %s AND role = ANY(%s)",
            (work_id, list(CREDIT_ROLES)),
        )
        for item in collapse_credits(credits):
            profile = credit_profile(item, profiles.get(item["mdl_id"]))
            profile["socials"] = fetch_person_socials(profile["mdl_url"])
            person_id = upsert_credit_person(conn, profile)
            grant_person_roles(conn, person_id, credit_role_codes(item["role"]))
            conn.execute(
                """
                INSERT INTO person_work (person_id, work_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (person_id, work_id, role) DO NOTHING
                """,
                (person_id, work_id, item["role"]),
            )
        conn.commit()
    return len(credits)


def _load_cast(slug: str) -> dict:
    base = os.environ.get("KURYANA_BASE_URL", "https://kuryana.tbdh.app").rstrip("/")
    request = urllib.request.Request(
        f"{base}/v2/dramas/{urllib.parse.quote(slug)}/cast",
        headers={"User-Agent": "glow-collect/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError("작가·감독을 읽지 못했습니다") from exc
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise ValueError("작가·감독을 읽지 못했습니다") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("작가·감독을 읽지 못했습니다")
    data = payload.get("data")
    raw = data.get("cast") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise ValueError("작가·감독 목록이 없습니다")
    return raw


def is_male(mdl_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT gender FROM person WHERE mdl_id = %s",
            (mdl_id,),
        ).fetchone()
    if row is not None and isinstance(row[0], str) and row[0].strip():
        return row[0].casefold() == "male"
    body, error = fetch_person(mdl_id)
    if error is not None or body is None:
        return False
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    gender = text_or_none(data.get("gender"))
    return gender is not None and gender.casefold() == "male"


def main_cast(slug: str) -> list[dict]:
    try:
        people = _load_cast(slug).get("Main Role")
    except ValueError:
        return []
    if not isinstance(people, list):
        return []
    found = []
    seen: set[str] = set()
    for item in people:
        if not isinstance(item, dict):
            continue
        mdl_id = person_mdl_id(item.get("slug") or "")
        if mdl_id is None or mdl_id in seen:
            continue
        seen.add(mdl_id)
        found.append({"mdl_id": mdl_id, "character": text_or_none(item.get("character"))})
    return found


def _main_actor(work_id: int, mdl_id: str) -> tuple[int | None, bool]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT p.id,
                   EXISTS (
                     SELECT 1 FROM person_work pw
                     WHERE pw.person_id = p.id AND pw.work_id = %s AND pw.role = 'Main Role'
                   )
            FROM person p
            WHERE p.mdl_id = %s
            """,
            (work_id, mdl_id),
        ).fetchone()
    if row is None:
        return None, False
    return int(row[0]), bool(row[1])


def save_missing_main_roles(work_id: int, slug: str) -> None:
    for item in main_cast(slug):
        mdl_id = item["mdl_id"]
        if is_male(mdl_id):
            continue
        person_id, linked = _main_actor(work_id, mdl_id)
        if linked:
            continue
        if person_id is None:
            try:
                person_id = register(mdl_id).person_id
            except Exception:
                continue
        link_main_role(work_id, person_id, item["character"])


def link_main_role(work_id: int, person_id: int, character: str | None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO person_work (person_id, work_id, role, character_name)
            VALUES (%s, %s, 'Main Role', %s)
            ON CONFLICT (person_id, work_id, role)
            DO UPDATE SET character_name = COALESCE(EXCLUDED.character_name, person_work.character_name)
            """,
            (person_id, work_id, character),
        )
        grant_person_roles(conn, person_id, ("a",))
        conn.commit()


def fetch_credits(slug: str) -> list[dict]:
    raw = _load_cast(slug)
    credits = []
    seen: set[tuple[str, str]] = set()
    for role, people in raw.items():
        if role not in CREDIT_ROLES or not isinstance(people, list):
            continue
        for item in people:
            if not isinstance(item, dict):
                continue
            mdl_id = person_mdl_id(item.get("slug") or "")
            name = text_or_none(item.get("name"))
            if mdl_id is None or name is None:
                continue
            key = (mdl_id, role)
            if key in seen:
                continue
            seen.add(key)
            credits.append(
                {
                    "mdl_id": mdl_id,
                    "role": role,
                    "name": name,
                    "image_url": text_or_none(item.get("image")),
                    "mdl_url": text_or_none(item.get("link")),
                }
            )
    order = {role: index for index, role in enumerate(CREDIT_ROLES)}
    credits.sort(key=lambda item: (order[item["role"]], item["name"]))
    return credits


def collapse_credits(credits: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in credits:
        current = grouped.get(item["mdl_id"])
        if current is None:
            grouped[item["mdl_id"]] = dict(item)
            continue
        roles = {current["role"], item["role"]}
        if roles <= {"Screenwriter"}:
            current["role"] = "Screenwriter"
        elif roles <= {"Director"}:
            current["role"] = "Director"
        else:
            current["role"] = "Screenwriter & Director"
    return list(grouped.values())


def move_credits(conn: psycopg.Connection) -> None:
    if conn.execute("SELECT to_regclass('public.screenwriter')").fetchone()[0] is None:
        return
    for table in ("screenwriter", "director"):
        conn.execute(
            f"""
            INSERT INTO person (
                mdl_id, name, native_name, first_name, family_name, stage_name,
                also_known_as, nationality, gender, born_text, image_url, mdl_url,
                about, collect_status, collected_at
            )
            SELECT mdl_id, name, native_name, first_name, family_name, stage_name,
                   also_known_as, nationality, gender, born_text, image_url, mdl_url,
                   NULL, 'collected', now()
            FROM {table}
            ON CONFLICT (mdl_id) DO NOTHING
            """
        )
    conn.execute(
        """
        INSERT INTO person_work (person_id, work_id, role)
        SELECT p.id, ws.work_id,
               CASE WHEN wd.work_id IS NOT NULL THEN 'Screenwriter & Director' ELSE 'Screenwriter' END
        FROM work_screenwriter ws
        JOIN screenwriter s ON s.id = ws.screenwriter_id
        JOIN person p ON p.mdl_id = s.mdl_id
        LEFT JOIN director d ON d.mdl_id = s.mdl_id
        LEFT JOIN work_director wd ON wd.director_id = d.id AND wd.work_id = ws.work_id
        ON CONFLICT (person_id, work_id, role) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO person_work (person_id, work_id, role)
        SELECT p.id, wd.work_id, 'Director'
        FROM work_director wd
        JOIN director d ON d.id = wd.director_id
        JOIN person p ON p.mdl_id = d.mdl_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM work_screenwriter ws
            JOIN screenwriter s ON s.id = ws.screenwriter_id
            WHERE s.mdl_id = d.mdl_id AND ws.work_id = wd.work_id
        )
        ON CONFLICT (person_id, work_id, role) DO NOTHING
        """
    )
    conn.execute("DROP TABLE work_screenwriter")
    conn.execute("DROP TABLE work_director")
    conn.execute("DROP TABLE screenwriter")
    conn.execute("DROP TABLE director")
    _fill_person_roles(conn)


def credit_profile(card: dict, body: dict | None) -> dict:
    data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
    name = text_or_none(data.get("name")) or card["name"]
    given, stage = given_and_stage(name, data.get("first_name"), data.get("family_name"))
    aliases = data.get("also_known_as")
    if not isinstance(aliases, list):
        aliases = []
    mdl_url = text_or_none(body.get("link")) if isinstance(body, dict) else None
    return {
        "mdl_id": card["mdl_id"],
        "name": name,
        "native_name": text_or_none(data.get("native_name")),
        "first_name": given,
        "family_name": text_or_none(data.get("family_name")),
        "stage_name": stage,
        "also_known_as": [item for item in aliases if isinstance(item, str)],
        "nationality": text_or_none(data.get("nationality")),
        "gender": text_or_none(data.get("gender")),
        "born_text": normalize_born(data.get("born")),
        "image_url": text_or_none(data.get("image")) or card.get("image_url"),
        "mdl_url": mdl_url or card.get("mdl_url"),
        "about": _biography(data.get("about")),
        "socials": [],
    }


def upsert_credit_person(conn: psycopg.Connection, profile: dict) -> int:
    row = conn.execute(
        """
        INSERT INTO person (
            mdl_id, name, native_name, first_name, family_name, stage_name,
            also_known_as, nationality, gender, born_text, image_url, about,
            socials, mdl_url, collect_status, collected_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'collected', now())
        ON CONFLICT (mdl_id) DO UPDATE
        SET name = COALESCE(EXCLUDED.name, person.name),
            native_name = COALESCE(EXCLUDED.native_name, person.native_name),
            first_name = COALESCE(EXCLUDED.first_name, person.first_name),
            family_name = COALESCE(EXCLUDED.family_name, person.family_name),
            stage_name = COALESCE(EXCLUDED.stage_name, person.stage_name),
            also_known_as = CASE
                WHEN cardinality(EXCLUDED.also_known_as) = 0 THEN person.also_known_as
                ELSE EXCLUDED.also_known_as
            END,
            nationality = COALESCE(EXCLUDED.nationality, person.nationality),
            gender = COALESCE(EXCLUDED.gender, person.gender),
            born_text = COALESCE(EXCLUDED.born_text, person.born_text),
            image_url = COALESCE(EXCLUDED.image_url, person.image_url),
            about = COALESCE(EXCLUDED.about, person.about),
            socials = CASE
                WHEN EXCLUDED.socials = '[]'::jsonb THEN person.socials
                ELSE EXCLUDED.socials
            END,
            mdl_url = COALESCE(EXCLUDED.mdl_url, person.mdl_url)
        WHERE person.deleted = 0
          AND NOT EXISTS (
            SELECT 1 FROM person_role
            WHERE person_id = person.id AND role_code = 'a'
        )
        RETURNING id
        """,
        (
            profile["mdl_id"],
            profile["name"],
            profile["native_name"],
            profile["first_name"],
            profile["family_name"],
            profile["stage_name"],
            profile["also_known_as"],
            profile["nationality"],
            profile["gender"],
            profile["born_text"],
            profile["image_url"],
            profile["about"],
            Json(profile.get("socials") or []),
            profile["mdl_url"],
        ),
    ).fetchone()
    if row:
        return int(row[0])
    row = conn.execute(
        "SELECT id FROM person WHERE mdl_id = %s",
        (profile["mdl_id"],),
    ).fetchone()
    return int(row[0])
