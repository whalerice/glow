import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

import psycopg

from app.ids import person_mdl_id, work_mdl_id

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
KINDS = {"Drama": "drama", "Movie": "movie"}
CREDIT_ROLES = ("Screenwriter & Director", "Director", "Screenwriter")


class DramaDetail(NamedTuple):
    image_url: str | None
    synopsis: str | None
    native_title: str | None
    tags: list[str]


class CollectResult(NamedTuple):
    mdl_id: str
    status: str
    person_id: int
    works: int = 0


def register(raw_id: str) -> CollectResult:
    mdl_id = person_mdl_id(raw_id)
    if mdl_id is None:
        raise ValueError("숫자 id가 아닙니다")

    with connect() as conn:
        apply_schema(conn)
        person_id = mark_registered(conn, mdl_id)
        conn.commit()

    body, error = fetch_person(mdl_id)
    posters = poster_map(body) if body is not None and error is None else {}
    with connect() as conn:
        if error is not None or body is None:
            mark_failed(conn, person_id, error or "success false")
            conn.commit()
            return CollectResult(mdl_id, "failed", person_id)
        try:
            link_count = save_success(conn, person_id, body, posters)
        except Exception as exc:
            conn.rollback()
            mark_failed(conn, person_id, str(exc))
            conn.commit()
            return CollectResult(mdl_id, "failed", person_id)
        conn.commit()
    return CollectResult(mdl_id, "collected", person_id, link_count)


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL이 없습니다")
    return psycopg.connect(url)


def apply_schema(conn: psycopg.Connection) -> None:
    script = SCHEMA_PATH.read_text()
    for statement in script.split(";"):
        sql = statement.strip()
        if sql:
            conn.execute(sql)


def mark_registered(conn: psycopg.Connection, mdl_id: str) -> int:
    row = conn.execute(
        """
        INSERT INTO person (mdl_id, collect_status)
        VALUES (%s, 'registered')
        ON CONFLICT (mdl_id) DO UPDATE
        SET collect_status = 'registered',
            collect_error = NULL,
            listed = true
        RETURNING id
        """,
        (mdl_id,),
    ).fetchone()
    return int(row[0])


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
    if not isinstance(data, dict):
        return None
    raw_tags = data.get("tags")
    if not isinstance(raw_tags, list):
        raw_tags = []
    return DramaDetail(
        text_or_none(data.get("poster")),
        text_or_none(data.get("synopsis")),
        text_or_none(data.get("native_title")),
        [item.strip() for item in raw_tags if isinstance(item, str) and item.strip()],
    )


def save_drama_detail(work_id: int) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT mdl_url, detail_at FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
    if row is None or row[1] is not None:
        return
    slug = drama_slug(row[0])
    if slug is None:
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
                image_url = COALESCE(%s, image_url),
                detail_at = now()
            WHERE id = %s AND detail_at IS NULL
            """,
            (detail.synopsis, detail.native_title, detail.tags, detail.image_url, work_id),
        )
        conn.commit()


def fill_drama_details() -> None:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, mdl_url FROM work WHERE detail_at IS NULL AND mdl_url IS NOT NULL"
        ).fetchall()
    for work_id, mdl_url in rows:
        slug = drama_slug(mdl_url)
        if slug is None:
            continue
        try:
            detail = fetch_drama_text(slug)
        except Exception:
            continue
        if detail is None:
            continue
        with connect() as conn:
            conn.execute(
                """
                UPDATE work
                SET synopsis = COALESCE(%s, synopsis),
                    native_title = COALESCE(%s, native_title),
                    tags = %s::text[],
                    image_url = COALESCE(%s, image_url),
                    detail_at = now()
                WHERE id = %s AND detail_at IS NULL
                """,
                (detail.synopsis, detail.native_title, detail.tags, detail.image_url, work_id),
            )
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
            text_or_none(data.get("born")),
            text_or_none(data.get("image")),
            text_or_none(body.get("link")),
            person_id,
        ),
    )

    links: dict[tuple[int, str], str | None] = {}
    works = data.get("works") if isinstance(data.get("works"), dict) else {}
    for source_kind, items in works.items():
        kind = KINDS.get(source_kind)
        if kind is None or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            work_id = upsert_work(conn, item, kind, posters.get(item.get("slug")))
            if work_id is None:
                continue
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
    return len(links)


def upsert_work(
    conn: psycopg.Connection,
    item: dict,
    kind: str,
    detail: DramaDetail | None,
) -> int | None:
    title = text_or_none(item.get("title"))
    if title is None:
        return None
    year = item.get("year") if isinstance(item.get("year"), int) else None
    episodes = item.get("episodes") if isinstance(item.get("episodes"), int) else None
    rating = item.get("rating") if isinstance(item.get("rating"), (int, float)) else None
    mdl_url = text_or_none(item.get("link"))
    mdl_id = work_mdl_id(item.get("slug"))
    image_url = detail.image_url if detail else None
    synopsis = detail.synopsis if detail else None
    native_title = detail.native_title if detail else None
    tags = detail.tags if detail else []
    fetched = detail is not None

    if mdl_id:
        row = conn.execute(
            """
            INSERT INTO work (
                mdl_id, title, kind, year, episodes, rating, mdl_url, image_url,
                synopsis, native_title, tags, detail_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::text[], CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT (mdl_id) DO UPDATE
            SET title = EXCLUDED.title,
                kind = EXCLUDED.kind,
                year = EXCLUDED.year,
                episodes = EXCLUDED.episodes,
                rating = EXCLUDED.rating,
                mdl_url = EXCLUDED.mdl_url,
                image_url = COALESCE(EXCLUDED.image_url, work.image_url),
                synopsis = COALESCE(EXCLUDED.synopsis, work.synopsis),
                native_title = COALESCE(EXCLUDED.native_title, work.native_title),
                tags = CASE WHEN %s THEN EXCLUDED.tags ELSE work.tags END,
                detail_at = CASE WHEN %s THEN now() ELSE work.detail_at END
            RETURNING id
            """,
            (
                mdl_id, title, kind, year, episodes, rating, mdl_url, image_url,
                synopsis, native_title, tags, fetched, fetched, fetched,
            ),
        ).fetchone()
        return int(row[0])

    row = conn.execute(
        """
        SELECT id FROM work
        WHERE mdl_id IS NULL
          AND title = %s
          AND year IS NOT DISTINCT FROM %s
          AND kind = %s
        """,
        (title, year, kind),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE work
            SET episodes = %s,
                rating = %s,
                mdl_url = %s,
                image_url = COALESCE(%s, image_url),
                synopsis = COALESCE(%s, synopsis),
                native_title = COALESCE(%s, native_title),
                tags = CASE WHEN %s THEN %s::text[] ELSE tags END,
                detail_at = CASE WHEN %s THEN now() ELSE detail_at END
            WHERE id = %s
            """,
            (
                episodes, rating, mdl_url, image_url, synopsis, native_title,
                fetched, tags or [], fetched, row[0],
            ),
        )
        return int(row[0])
    row = conn.execute(
        """
        INSERT INTO work (
            title, kind, year, episodes, rating, mdl_url, image_url,
            synopsis, native_title, tags, detail_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::text[], CASE WHEN %s THEN now() ELSE NULL END)
        RETURNING id
        """,
        (
            title, kind, year, episodes, rating, mdl_url, image_url,
            synopsis, native_title, tags, fetched,
        ),
    ).fetchone()
    return int(row[0])


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


def text_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


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
            person_id = upsert_credit_person(conn, credit_profile(item, profiles.get(item["mdl_id"])))
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


def fetch_credits(slug: str) -> list[dict]:
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
                about, collect_status, collected_at, listed
            )
            SELECT mdl_id, name, native_name, first_name, family_name, stage_name,
                   also_known_as, nationality, gender, born_text, image_url, mdl_url,
                   NULL, 'collected', now(), false
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
        "born_text": text_or_none(data.get("born")),
        "image_url": text_or_none(data.get("image")) or card.get("image_url"),
        "mdl_url": mdl_url or card.get("mdl_url"),
    }


def upsert_credit_person(conn: psycopg.Connection, profile: dict) -> int:
    row = conn.execute(
        """
        INSERT INTO person (
            mdl_id, name, native_name, first_name, family_name, stage_name,
            also_known_as, nationality, gender, born_text, image_url, about,
            mdl_url, collect_status, collected_at, listed
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, 'collected', now(), false)
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
            mdl_url = COALESCE(EXCLUDED.mdl_url, person.mdl_url)
        WHERE person.listed = false
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
