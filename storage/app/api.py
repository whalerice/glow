import json
import re
import urllib.error
from datetime import date, datetime
from decimal import Decimal
from threading import Lock, Thread

from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.agency import save_sapphic_company, save_wiki_spells
from app.collect import (
    CREDIT_ROLES,
    collect_credits,
    collect_episodes,
    connect,
    drama_slug,
    register,
    register_work,
    refresh_work,
    save_drama_detail,
    save_where_to_watch,
)
from app.fandom import SOURCE as FANDOM_SOURCE
from app.fandom import fetch_page, search as fandom_search, selected_payload as fandom_payload
from app.sapphic import SOURCE, fetch_star, search, selected_payload
from app.tmdb import save_tmdb
from app.wikipedia import SOURCE as WIKI_SOURCE
from app.wikipedia import fetch_page as fetch_wiki
from app.wikipedia import gaps, search as wiki_search, selected_payload as wiki_payload

_LOCK = Lock()
_ON = False
_DONE = 0
_TOTAL = 0
_NAME = ""
_WIKI_FIELDS = (
    "image",
    "birth_name",
    "native_name",
    "birthday",
    "birth_place",
    "height",
    "education",
    "years_active",
    "agent",
    "career",
    "fashion",
    "ambassadorship",
    "accolades",
)


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


def encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value))


def dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=encode).encode()


def dispatch(method: str, path: str, query: dict, body: dict | None) -> tuple[int, dict]:
    try:
        return _route(method, path, query, body or {})
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _route(method: str, path: str, query: dict, body: dict) -> tuple[int, dict]:
    if path == "/api/people/works/progress" and method == "GET":
        return 200, progress_payload()
    if path == "/api/people/works" and method == "POST":
        start_work_refresh()
        return 202, {"on": True}
    if path == "/api/people" and method == "GET":
        return 200, {"people": listed_people()}
    if path == "/api/people" and method == "POST":
        return 200, _register(body)
    if path == "/api/works/collect" and method == "POST":
        start_tmdb_collect(_ids(body))
        return 202, tmdb_progress()
    if path == "/api/works/collect/progress" and method == "GET":
        return 200, tmdb_progress()
    if path == "/api/works/episodes" and method == "POST":
        start_episode_collect()
        return 202, episode_progress()
    if path == "/api/works/episodes/progress" and method == "GET":
        return 200, episode_progress()
    if path == "/api/works" and method == "GET":
        return 200, works_payload(query)
    if path == "/api/works" and method == "POST":
        return 200, _register_work(body)
    if path == "/api/works/exception" and method == "POST":
        deleted = 0 if body.get("deleted") in (0, "0") else 1
        return 200, {"ok": True, "count": hide_works(_ids(body), deleted)}
    if path == "/api/works/delete" and method == "POST":
        return 200, {"ok": True, "count": delete_works(_ids(body))}
    if path == "/api/credits" and method == "GET":
        return 200, {"credits": credit_rows()}
    if path == "/api/companies" and method == "GET":
        return 200, {"companies": company_rows()}
    person = re.fullmatch(r"/api/people/(\d+)", path)
    person_sapphic = re.fullmatch(r"/api/people/(\d+)/sapphic", path)
    person_fandom = re.fullmatch(r"/api/people/(\d+)/fandom", path)
    person_wiki = re.fullmatch(r"/api/people/(\d+)/wiki", path)
    person_delete = re.fullmatch(r"/api/people/(\d+)/delete", path)
    work = re.fullmatch(r"/api/works/(\d+)", path)
    work_exception = re.fullmatch(r"/api/works/(\d+)/exception", path)
    work_delete = re.fullmatch(r"/api/works/(\d+)/delete", path)
    work_episodes = re.fullmatch(r"/api/works/(\d+)/episodes", path)
    work_credits = re.fullmatch(r"/api/works/(\d+)/credits", path)
    work_tmdb = re.fullmatch(r"/api/works/(\d+)/tmdb", path)
    credit = re.fullmatch(r"/api/credits/(\d+)", path)
    company = re.fullmatch(r"/api/companies/(\d+)", path)
    if person_sapphic and method == "GET":
        return 200, sapphic_search_payload(int(person_sapphic.group(1)), _one(query, "q", ""))
    if person_sapphic and method == "POST":
        save_sapphic(int(person_sapphic.group(1)), str(body.get("slug") or ""), _fields(body))
        return 200, {"ok": True}
    if person_fandom and method == "GET":
        return 200, fandom_search_payload(int(person_fandom.group(1)), _one(query, "q", ""))
    if person_fandom and method == "POST":
        save_fandom(int(person_fandom.group(1)), str(body.get("title") or ""), _fields(body))
        return 200, {"ok": True}
    if person_wiki and method == "GET":
        return 200, wiki_search_payload(int(person_wiki.group(1)), _one(query, "q", ""))
    if person_wiki and method == "POST":
        save_wiki(
            int(person_wiki.group(1)),
            str(body.get("title") or ""),
            _fields(body),
            str(body.get("lang") or "en"),
        )
        return 200, {"ok": True}
    if person_delete and method == "POST":
        if not delete_person(int(person_delete.group(1))):
            raise ApiError(404, "없는 배우입니다.")
        return 200, {"ok": True}
    if person and method == "GET":
        return 200, person_payload(int(person.group(1)))
    if work_exception and method == "POST":
        work_id = int(work_exception.group(1))
        deleted = 0 if body.get("deleted") in (0, "0") else 1
        hide_work(work_id, deleted)
        return 200, {"ok": True, "deleted": deleted}
    if work_delete and method == "POST":
        if not delete_work(int(work_delete.group(1))):
            raise ApiError(404, "없는 작품입니다.")
        return 200, {"ok": True}
    if work_episodes and method == "POST":
        collect_episodes(int(work_episodes.group(1)))
        return 200, {"ok": True}
    if work_credits and method == "POST":
        collect_credits(int(work_credits.group(1)))
        return 200, {"ok": True}
    if work_tmdb and method == "POST":
        work_id = int(work_tmdb.group(1))
        save_tmdb(work_id, str(body.get("tmdb_id") or ""), str(body.get("tmdb_kind") or ""))
        _save_mdl_watch(work_id)
        return 200, {"ok": True}
    if work and method == "GET":
        return 200, work_payload(int(work.group(1)))
    if credit and method == "GET":
        return 200, credit_payload(int(credit.group(1)))
    if company and method == "GET":
        return 200, company_payload(int(company.group(1)))
    if company and method == "POST":
        save_company_urls(
            int(company.group(1)),
            str(body.get("logo_url") or ""),
            str(body.get("homepage") or ""),
        )
        return 200, {"ok": True}
    raise ApiError(404, "없는 화면입니다.")


def _one(query: dict, key: str, default: str) -> str:
    values = query.get(key) or [default]
    return values[0] if values else default


def _fields(body: dict) -> list[str]:
    raw = body.get("fields") or []
    if not isinstance(raw, list):
        raise ApiError(400, "JSON 객체가 아닙니다")
    return [item for item in raw if isinstance(item, str)]


def _register(body: dict) -> dict:
    result = register(str(body.get("mdl_id") or ""))
    return {
        "person_id": result.person_id,
        "mdl_id": result.mdl_id,
        "status": result.status,
        "works": result.works,
    }


def _register_work(body: dict) -> dict:
    work_id, mdl_id, exists = register_work(str(body.get("mdl_id") or ""))
    return {"work_id": work_id, "mdl_id": mdl_id, "exists": exists}


def _counts(rows: list[dict], *keys: str) -> list[dict]:
    for row in rows:
        for key in keys:
            if row.get(key) is not None:
                row[key] = int(row[key])
    return rows


def listed_people() -> list[dict]:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT p.id, p.mdl_id, p.name, p.native_name, p.nationality,
                   p.image_url, p.collect_status, p.collected_at,
                   c.works, c.hidden,
                   EXISTS (
                     SELECT 1 FROM person_source s
                     WHERE s.person_id = p.id AND s.source = %s
                   ) AS sapphic,
                   EXISTS (
                     SELECT 1 FROM person_source s
                     WHERE s.person_id = p.id AND s.source = %s
                   ) AS wiki
            FROM person p
            LEFT JOIN LATERAL (
              SELECT count(*) FILTER (WHERE w.deleted = 0) AS works,
                     count(*) FILTER (WHERE w.deleted = 1) AS hidden
              FROM person_work pw
              JOIN work w ON w.id = pw.work_id
              WHERE pw.person_id = p.id
                AND NOT (pw.role = ANY(%s))
            ) c ON true
            WHERE EXISTS (
              SELECT 1 FROM person_role pr
              WHERE pr.person_id = p.id AND pr.role_code = 'a'
            )
            ORDER BY p.id DESC
            """,
            (SOURCE, WIKI_SOURCE, list(CREDIT_ROLES)),
        ).fetchall()
    return _counts(rows, "works", "hidden")


def work_state() -> tuple[bool, int, int, str]:
    with _LOCK:
        return _ON, _DONE, _TOTAL, _NAME


def progress_payload() -> dict:
    on, done, total, name = work_state()
    return {"on": on, "done": done, "total": total, "name": name, "rows": listed_people()}


_EP_LOCK = Lock()
_EP_ON = False
_EP_DONE = 0
_EP_TOTAL = 0
_EP_NAME = ""


_TMDB_LOCK = Lock()
_TMDB_ON = False
_TMDB_DONE = 0
_TMDB_TOTAL = 0
_TMDB_NAME = ""


def tmdb_progress() -> dict:
    with _TMDB_LOCK:
        return {"on": _TMDB_ON, "done": _TMDB_DONE, "total": _TMDB_TOTAL, "name": _TMDB_NAME}


def start_tmdb_collect(ids: list[int]) -> None:
    global _TMDB_ON, _TMDB_DONE, _TMDB_TOTAL, _TMDB_NAME
    if not ids:
        return
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title FROM work WHERE id = ANY(%s) ORDER BY id",
            (ids,),
        ).fetchall()
    with _TMDB_LOCK:
        if _TMDB_ON or not rows:
            return
        _TMDB_ON = True
        _TMDB_DONE = 0
        _TMDB_TOTAL = len(rows)
        _TMDB_NAME = rows[0][1]
    Thread(target=_recollect_tmdb, args=(rows,), daemon=True).start()


def _recollect_tmdb(rows: list) -> None:
    global _TMDB_ON, _TMDB_DONE, _TMDB_NAME
    try:
        for index, (work_id, title) in enumerate(rows):
            with _TMDB_LOCK:
                _TMDB_NAME = title or ""
                _TMDB_DONE = index
            try:
                refresh_work(int(work_id))
            except Exception:
                continue
        with _TMDB_LOCK:
            _TMDB_DONE = len(rows)
    finally:
        with _TMDB_LOCK:
            _TMDB_ON = False


def episode_progress() -> dict:
    with _EP_LOCK:
        return {"on": _EP_ON, "done": _EP_DONE, "total": _EP_TOTAL, "name": _EP_NAME}


def start_episode_collect() -> None:
    global _EP_ON, _EP_DONE, _EP_TOTAL, _EP_NAME
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title FROM work
            WHERE deleted = 0 AND kind = 'drama'
            ORDER BY id
            """
        ).fetchall()
    with _EP_LOCK:
        if _EP_ON or not rows:
            return
        _EP_ON = True
        _EP_DONE = 0
        _EP_TOTAL = len(rows)
        _EP_NAME = rows[0][1]
    Thread(target=_collect_episodes, args=(rows,), daemon=True).start()


def _collect_episodes(rows: list) -> None:
    global _EP_ON, _EP_DONE, _EP_NAME
    try:
        for index, (work_id, title) in enumerate(rows):
            with _EP_LOCK:
                _EP_NAME = title
                _EP_DONE = index
            try:
                collect_episodes(int(work_id))
            except Exception:
                continue
        with _EP_LOCK:
            _EP_DONE = len(rows)
    finally:
        with _EP_LOCK:
            _EP_ON = False


def start_work_refresh() -> None:
    global _ON, _DONE, _TOTAL, _NAME
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT p.mdl_id, COALESCE(NULLIF(p.name, ''), p.mdl_id)
            FROM person p
            WHERE EXISTS (
              SELECT 1 FROM person_role pr
              WHERE pr.person_id = p.id AND pr.role_code = 'a'
            )
            ORDER BY p.id
            """
        ).fetchall()
    with _LOCK:
        if _ON or not rows:
            return
        _ON = True
        _DONE = 0
        _TOTAL = len(rows)
        _NAME = rows[0][1]
    Thread(target=_refresh_listed_works, args=(rows,), daemon=True).start()


def _refresh_listed_works(rows: list) -> None:
    global _ON, _DONE, _NAME
    try:
        for index, (mdl_id, name) in enumerate(rows):
            with _LOCK:
                _NAME = name
                _DONE = index
            try:
                register(str(mdl_id))
            except Exception:
                continue
        with _LOCK:
            _DONE = len(rows)
    finally:
        with _LOCK:
            _ON = False


def delete_person(person_id: int) -> bool:
    with connect() as conn:
        actor = conn.execute(
            "SELECT 1 FROM person_role WHERE person_id = %s AND role_code = 'a'",
            (person_id,),
        ).fetchone()
        if actor is None:
            return False
        conn.execute("DELETE FROM person_work WHERE person_id = %s", (person_id,))
        conn.execute("DELETE FROM person_source WHERE person_id = %s", (person_id,))
        conn.execute("DELETE FROM person_company WHERE person_id = %s", (person_id,))
        conn.execute("DELETE FROM person_ship WHERE person_id = %s", (person_id,))
        conn.execute(
            """
            DELETE FROM ship
            WHERE NOT EXISTS (
              SELECT 1 FROM person_ship WHERE person_ship.ship_id = ship.id
            )
            """
        )
        conn.execute("DELETE FROM person_role WHERE person_id = %s", (person_id,))
        conn.execute("DELETE FROM person WHERE id = %s", (person_id,))
        conn.commit()
    return True


def _ids(body: dict) -> list[int]:
    raw = body.get("ids")
    if not isinstance(raw, list):
        return []
    ids = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str) and item.isdigit():
            ids.append(int(item))
    return ids


def hide_works(ids: list[int], deleted: int) -> int:
    if not ids:
        return 0
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE work SET deleted = %s WHERE id = ANY(%s)",
            (deleted, ids),
        )
        conn.commit()
    return cursor.rowcount


def _save_mdl_watch(work_id: int) -> None:
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT mdl_url FROM work WHERE id = %s",
                (work_id,),
            ).fetchone()
        if row is None:
            return
        slug = drama_slug(row[0])
        if slug is None:
            return
        save_where_to_watch(work_id, slug)
    except Exception:
        pass


def delete_works(ids: list[int]) -> int:
    if not ids:
        return 0
    with connect() as conn:
        for table in ("episode", "person_work", "work_company", "work_provider", "work_watch"):
            conn.execute(f"DELETE FROM {table} WHERE work_id = ANY(%s)", (ids,))
        cursor = conn.execute("DELETE FROM work WHERE id = ANY(%s)", (ids,))
        conn.commit()
    return cursor.rowcount


def delete_work(work_id: int) -> bool:
    with connect() as conn:
        found = conn.execute("SELECT 1 FROM work WHERE id = %s", (work_id,)).fetchone()
        if found is None:
            return False
        for table in ("episode", "person_work", "work_company", "work_provider", "work_watch"):
            conn.execute(f"DELETE FROM {table} WHERE work_id = %s", (work_id,))
        conn.execute("DELETE FROM work WHERE id = %s", (work_id,))
        conn.commit()
    return True


def hide_work(work_id: int, deleted: int = 1) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE work SET deleted = %s WHERE id = %s",
            (deleted, work_id),
        )
        conn.commit()


def person_payload(person_id: int) -> dict:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute("SELECT * FROM person WHERE id = %s", (person_id,)).fetchone()
        if person is None:
            raise ApiError(404, "없는 배우입니다.")
        sources = conn.execute(
            """
            SELECT source, display_name, external_key, payload, selected_at
            FROM person_source
            WHERE person_id = %s
            """,
            (person_id,),
        ).fetchall()
        works = conn.execute(
            """
            SELECT w.id, w.title, w.kind, w.year, w.episodes, w.rating, w.mdl_id,
                   w.image_url, w.tags, w.queer, queer.name AS queer_name, pw.role, pw.character_name
            FROM person_work pw
            JOIN work w ON w.id = pw.work_id
            LEFT JOIN queer ON queer.id = w.queer
            WHERE pw.person_id = %s AND w.deleted = 0 AND NOT (pw.role = ANY(%s))
            ORDER BY w.year DESC NULLS FIRST, w.title
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchall()
        actor = conn.execute(
            "SELECT 1 FROM person_role WHERE person_id = %s AND role_code = 'a'",
            (person_id,),
        ).fetchone()
        affiliations = conn.execute(
            """
            SELECT c.id AS company_id, c.name, pc.start_year, pc.end_year,
                   pc.period_text, pc.is_current
            FROM person_company pc
            JOIN company c ON c.id = pc.company_id
            WHERE pc.person_id = %s AND pc.relation = 'agency'
            ORDER BY pc.is_current DESC, pc.start_year NULLS LAST, c.name
            """,
            (person_id,),
        ).fetchall()
    by_source = {row["source"]: row for row in sources}
    return {
        "person": person,
        "works": works,
        "affiliations": affiliations,
        "ships": linked_ships(person_id),
        "actor": actor is not None,
        "sources": {
            SOURCE: by_source.get(SOURCE),
            FANDOM_SOURCE: by_source.get(FANDOM_SOURCE),
            WIKI_SOURCE: by_source.get(WIKI_SOURCE),
        },
    }


_PAGE_SIZES = (20, 50, 100)
_STATUSES = {
    "Returning Series",
    "Planned",
    "In Production",
    "Post Production",
    "Pilot",
    "Ended",
    "Canceled",
    "Released",
    "Rumored",
}
_SORTS = {
    "title": "w.title",
    "queer": "queer.name",
    "kind": "CASE w.kind WHEN 'drama' THEN '드라마' WHEN 'movie' THEN '영화' WHEN 'tv_show' THEN 'TV 쇼' ELSE w.kind END",
    "year": "w.year",
    "episodes": "w.episodes",
    "rating": "w.rating",
    "tmdb_status": "w.tmdb_status",
    "cast_count": "cast_count",
}


def _page(query: dict) -> int:
    try:
        page = int(_one(query, "page", "1"))
    except ValueError:
        return 1
    return page if page > 0 else 1


def _page_size(query: dict) -> int:
    try:
        size = int(_one(query, "size", "20"))
    except ValueError:
        return 20
    return size if size in _PAGE_SIZES else 20


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def works_payload(query: dict) -> dict:
    mode = _one(query, "deleted", "0")
    if mode not in ("all", "0", "1"):
        mode = "0"
    page = _page(query)
    size = _page_size(query)
    needle = _one(query, "q", "").strip()
    queer = _one(query, "queer", "")
    status = _one(query, "status", "")
    sort = _one(query, "sort", "")
    desc = _one(query, "dir", "") == "desc"
    filters: list[str] = []
    params: list = []
    if mode == "0":
        filters.append("w.deleted = 0")
    elif mode == "1":
        filters.append("w.deleted = 1")
    if needle:
        filters.append("(w.title ILIKE %s ESCAPE '\\' OR w.ko_title ILIKE %s ESCAPE '\\')")
        like = _like(needle)
        params.extend((like, like))
    if queer == "none":
        filters.append("w.queer IS NULL")
    elif queer in ("BL", "GL", "LGBTQ"):
        filters.append("queer.name = %s")
        params.append(queer)
    if status == "none":
        filters.append("(w.tmdb_status IS NULL OR btrim(w.tmdb_status) = '')")
    elif status in _STATUSES:
        filters.append("w.tmdb_status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    if sort == "tmdb_id":
        order = "(w.tmdb_id IS NULL), w.year DESC NULLS FIRST, w.title"
    elif sort in _SORTS:
        direction = "DESC" if desc else "ASC"
        order = f"{_SORTS[sort]} {direction} NULLS LAST, w.year DESC NULLS FIRST, w.title"
    else:
        order = "w.year DESC NULLS FIRST, w.title"
    with connect() as conn:
        conn.row_factory = dict_row
        total = int(
            conn.execute(
                f"""
                SELECT count(*)
                FROM work w
                LEFT JOIN queer ON queer.id = w.queer
                {where}
                """,
                params,
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT w.id, w.title, w.ko_title, w.kind, w.year, w.episodes, w.rating, w.image_url, w.tags,
                   w.queer, queer.name AS queer_name, w.tmdb_id, w.tmdb_status, w.deleted,
                   (SELECT count(*) FROM person_work pw
                    WHERE pw.work_id = w.id AND NOT (pw.role = ANY(%s))) AS cast_count
            FROM work w
            LEFT JOIN queer ON queer.id = w.queer
            {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s
            """,
            [list(CREDIT_ROLES), *params, size, (page - 1) * size],
        ).fetchall()
        faces: dict[int, list[dict]] = {}
        ids = [row["id"] for row in rows]
        if ids:
            seen: set[tuple[int, int]] = set()
            for item in conn.execute(
                """
                SELECT pw.work_id, p.id, p.name, p.image_url
                FROM person_work pw
                JOIN person p ON p.id = pw.person_id
                WHERE pw.work_id = ANY(%s) AND NOT (pw.role = ANY(%s))
                ORDER BY p.name
                """,
                (ids, list(CREDIT_ROLES)),
            ).fetchall():
                key = (item["work_id"], item["id"])
                if key in seen:
                    continue
                seen.add(key)
                faces.setdefault(item["work_id"], []).append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "image_url": item["image_url"],
                    }
                )
        for row in rows:
            row["cast"] = faces.get(row["id"], [])
    return {
        "deleted": mode,
        "page": page,
        "total": total,
        "works": _counts(rows, "cast_count"),
    }


def work_payload(work_id: int) -> dict:
    with connect() as conn:
        found = conn.execute("SELECT 1 FROM work WHERE id = %s", (work_id,)).fetchone()
    if found is None:
        raise ApiError(404, "없는 작품입니다.")
    save_drama_detail(work_id)
    with connect() as conn:
        conn.row_factory = dict_row
        work = conn.execute("SELECT * FROM work WHERE id = %s", (work_id,)).fetchone()
        if work is None:
            raise ApiError(404, "없는 작품입니다.")
        cast = conn.execute(
            """
            SELECT p.id, p.name, p.native_name, pw.role, pw.character_name
            FROM person_work pw
            JOIN person p ON p.id = pw.person_id
            WHERE pw.work_id = %s AND NOT (pw.role = ANY(%s))
            ORDER BY p.name
            """,
            (work_id, list(CREDIT_ROLES)),
        ).fetchall()
        episodes = []
        if work["kind"] != "movie":
            episodes = conn.execute(
                """
                SELECT number, title, air_date, rating, votes, image_url, mdl_url, summary
                FROM episode
                WHERE work_id = %s
                ORDER BY number
                """,
                (work_id,),
            ).fetchall()
        credits = conn.execute(
            """
            SELECT p.id, p.name, p.native_name, p.image_url, pw.role
            FROM person_work pw
            JOIN person p ON p.id = pw.person_id
            WHERE pw.work_id = %s AND pw.role = ANY(%s)
            ORDER BY p.name
            """,
            (work_id, list(CREDIT_ROLES)),
        ).fetchall()
        providers = conn.execute(
            """
            SELECT country, name, offer, url
            FROM work_provider
            WHERE work_id = %s
            ORDER BY country, name
            """,
            (work_id,),
        ).fetchall()
        networks = conn.execute(
            """
            SELECT c.id, c.name
            FROM work_company wc
            JOIN company c ON c.id = wc.company_id
            JOIN company_type l ON l.company_id = c.id
            JOIN org_type t ON t.id = l.org_type_id AND t.name = '방송사'
            WHERE wc.work_id = %s
            ORDER BY c.name
            """,
            (work_id,),
        ).fetchall()
        watches = conn.execute(
            """
            SELECT name, offer, url
            FROM work_provider
            WHERE work_id = %s AND country = ''
            ORDER BY name, offer
            """,
            (work_id,),
        ).fetchall()
    order = {role: index for index, role in enumerate(CREDIT_ROLES)}
    credits.sort(key=lambda row: (order.get(row["role"], len(order)), row["name"] or ""))
    return {
        "work": work,
        "cast": cast,
        "episodes": episodes,
        "credits": credits,
        "providers": providers,
        "networks": networks,
        "watches": watches,
    }


def credit_rows() -> list[dict]:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.native_name, p.nationality, p.image_url,
                   array_agg(DISTINCT pw.role) AS roles,
                   count(DISTINCT pw.work_id) AS works
            FROM person p
            JOIN person_work pw ON pw.person_id = p.id
            JOIN work w ON w.id = pw.work_id AND w.deleted = 0
            WHERE pw.role = ANY(%s)
            GROUP BY p.id
            ORDER BY p.name
            """,
            (list(CREDIT_ROLES),),
        ).fetchall()
    return _counts(rows, "works")


def credit_payload(person_id: int) -> dict:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            """
            SELECT p.*
            FROM person p
            WHERE p.id = %s
              AND EXISTS (
                SELECT 1 FROM person_work pw
                JOIN work w ON w.id = pw.work_id AND w.deleted = 0
                WHERE pw.person_id = p.id AND pw.role = ANY(%s)
              )
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchone()
        if person is None:
            raise ApiError(404, "없는 작가·감독입니다.")
        works = conn.execute(
            """
            SELECT w.id, w.title, w.kind, w.year, pw.role
            FROM person_work pw
            JOIN work w ON w.id = pw.work_id
            WHERE pw.person_id = %s AND w.deleted = 0 AND pw.role = ANY(%s)
            ORDER BY w.year DESC NULLS LAST, w.title
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchall()
    return {"person": person, "works": works}


def company_rows() -> list[dict]:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.logo_url,
                   (SELECT count(*) FROM person_company pc WHERE pc.company_id = c.id) AS members,
                   COALESCE((
                       SELECT string_agg(
                           ct.name, ', '
                           ORDER BY array_position(
                               ARRAY['제작사','배급사','방송사','엔터테이먼트'], ct.name
                           )
                       )
                       FROM company_type l
                       JOIN org_type ct ON ct.id = l.org_type_id
                       WHERE l.company_id = c.id
                   ), '') AS types
            FROM company c
            ORDER BY c.name
            """
        ).fetchall()
    return _counts(rows, "members")


def company_payload(company_id: int) -> dict:
    with connect() as conn:
        conn.row_factory = dict_row
        company = conn.execute("SELECT * FROM company WHERE id = %s", (company_id,)).fetchone()
        if company is None:
            raise ApiError(404, "없는 종합 콘텐츠 스튜디오입니다.")
        types = conn.execute(
            """
            SELECT ct.name
            FROM company_type l
            JOIN org_type ct ON ct.id = l.org_type_id
            WHERE l.company_id = %s
            ORDER BY array_position(ARRAY['제작사','배급사','방송사','엔터테이먼트'], ct.name)
            """,
            (company_id,),
        ).fetchall()
        works = conn.execute(
            """
            SELECT w.id, w.title, w.year
            FROM work_company wc
            JOIN work w ON w.id = wc.work_id
            WHERE wc.company_id = %s AND w.deleted = 0
            ORDER BY w.year DESC NULLS LAST, w.title
            """,
            (company_id,),
        ).fetchall()
        people = conn.execute(
            """
            SELECT p.id, p.name, p.native_name, pc.period_text, pc.is_current, pc.start_year
            FROM person_company pc
            JOIN person p ON p.id = pc.person_id
            WHERE pc.company_id = %s AND pc.relation = 'agency'
            ORDER BY pc.start_year NULLS LAST, p.name
            """,
            (company_id,),
        ).fetchall()
    return {
        "company": company,
        "types": [row["name"] for row in types],
        "works": works,
        "people": people,
    }


def save_company_urls(company_id: int, logo: str, homepage: str) -> None:
    logo = logo.strip()
    homepage = homepage.strip()
    if logo and not logo.startswith(("http://", "https://")):
        raise ValueError("로고 주소가 아닙니다")
    if homepage and not homepage.startswith(("http://", "https://")):
        raise ValueError("홈페이지 주소가 아닙니다")
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM company WHERE id = %s", (company_id,)).fetchone()
        if row is None:
            raise ValueError("없는 종합 콘텐츠 스튜디오입니다")
        conn.execute(
            "UPDATE company SET logo_url = %s, homepage = %s WHERE id = %s",
            (logo or None, homepage or None, company_id),
        )
        conn.commit()


def _search_base(person_id: int) -> dict:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            "SELECT id, name, stage_name, mdl_id FROM person WHERE id = %s",
            (person_id,),
        ).fetchone()
    if person is None:
        raise ApiError(404, "없는 배우입니다.")
    return person


def _search_body(person: dict, query: str, blocked: bool = False, message: str = "", hint: str = "", allowed: list | None = None, profiles: list | None = None) -> dict:
    return {
        "person": {
            "id": person["id"],
            "name": person["name"],
            "stage_name": person["stage_name"],
            "mdl_id": person["mdl_id"],
        },
        "query": query,
        "blocked": blocked,
        "message": message,
        "hint": hint,
        "allowed": allowed or [],
        "profiles": profiles or [],
    }


def _load(query: str, loader) -> tuple[list, str]:
    if not query.strip():
        return [], ""
    try:
        profiles = loader(query)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ApiError(502, str(exc)) from exc
    return profiles, ""


def sapphic_search_payload(person_id: int, query: str) -> dict:
    person = _search_base(person_id)
    active = query or person["name"] or ""
    profiles, _message = _load(active, search)
    message = "맞는 스타 페이지가 없습니다." if active.strip() and not profiles else ""
    return _search_body(person, active, message=message, profiles=profiles)


def fandom_search_payload(person_id: int, query: str) -> dict:
    person = _search_base(person_id)
    with connect() as conn:
        conn.row_factory = dict_row
        sapphic = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, SOURCE),
        ).fetchone()
    active = query or person["stage_name"] or person["name"] or ""
    if not is_gmmtv(sapphic):
        return _search_body(
            person,
            active,
            blocked=True,
            message="Sapphic Effect 소속사가 GMMTV일 때만 GMMTV Wiki를 찾는다.",
        )
    profiles, _message = _load(active, fandom_search)
    message = "맞는 위키 문서가 없습니다." if active.strip() and not profiles else ""
    return _search_body(person, active, message=message, profiles=profiles)


def wiki_search_payload(person_id: int, query: str) -> dict:
    person = _search_base(person_id)
    with connect() as conn:
        conn.row_factory = dict_row
        sapphic = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, SOURCE),
        ).fetchone()
        fandom = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, FANDOM_SOURCE),
        ).fetchone()
    allowed_set = gaps(fandom["payload"] if fandom else None)
    allowed = [key for key in _WIKI_FIELDS if key in allowed_set]
    active = query or person["name"] or ""
    hint = (
        "GMMTV Wiki에 없는 항목만 보인다."
        if is_gmmtv(sapphic)
        else "고른 항목만 이 배우의 위키 출처로 저장한다. 영어에 없으면 프랑스 위키를 본다."
    )
    profiles, _message = _load(active, wiki_search)
    message = "맞는 위키 문서가 없습니다." if active.strip() and not profiles else ""
    return _search_body(person, active, message=message, hint=hint, allowed=allowed, profiles=profiles)


def is_gmmtv(source: dict | None) -> bool:
    if source is None or not isinstance(source["payload"], dict):
        return False
    company = source["payload"].get("company") or {}
    if not isinstance(company, dict):
        return False
    name = str(company.get("name") or "").strip().lower()
    slug = str(company.get("slug") or "").strip().lower()
    return name == "gmmtv" or slug == "gmmtv"


def save_fandom(person_id: int, title: str, fields: list[str]) -> None:
    try:
        profile = fetch_page(title)
    except urllib.error.URLError as exc:
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
    if profile is None:
        raise ValueError("인물 문서가 아닙니다")
    payload = fandom_payload(profile, fields)
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM person WHERE id = %s", (person_id,)).fetchone()
        if exists is None:
            raise ValueError("없는 배우입니다")
        taken = conn.execute(
            """
            SELECT person_id FROM person_source
            WHERE source = %s AND external_key = %s AND person_id <> %s
            """,
            (FANDOM_SOURCE, profile["title"], person_id),
        ).fetchone()
        if taken:
            raise ValueError("이미 다른 배우에 연결된 위키 문서입니다")
        conn.execute(
            """
            INSERT INTO person_source (person_id, source, external_key, display_name, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (person_id, source) DO UPDATE
            SET external_key = EXCLUDED.external_key,
                display_name = EXCLUDED.display_name,
                payload = EXCLUDED.payload,
                selected_at = now()
            """,
            (person_id, FANDOM_SOURCE, profile["title"], profile["name"], Json(payload)),
        )
        conn.commit()


def _wiki_key(profile: dict) -> str:
    language = profile.get("language") or "en"
    if language == "en":
        return profile["title"]
    return f"{language}:{profile['title']}"


def save_wiki(person_id: int, title: str, fields: list[str], language: str = "en") -> None:
    profile = fetch_wiki(title, language)
    if profile is None:
        raise ValueError("인물 문서가 아닙니다")
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM person WHERE id = %s", (person_id,)).fetchone()
        if exists is None:
            raise ValueError("없는 배우입니다")
        fandom = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, FANDOM_SOURCE),
        ).fetchone()
        payload = wiki_payload(profile, fields, gaps(fandom[0] if fandom else None))
        taken = conn.execute(
            """
            SELECT person_id FROM person_source
            WHERE source = %s AND external_key = %s AND person_id <> %s
            """,
            (WIKI_SOURCE, _wiki_key(profile), person_id),
        ).fetchone()
        if taken:
            raise ValueError("이미 다른 배우에 연결된 위키 문서입니다")
        conn.execute(
            """
            INSERT INTO person_source (person_id, source, external_key, display_name, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (person_id, source) DO UPDATE
            SET external_key = EXCLUDED.external_key,
                display_name = EXCLUDED.display_name,
                payload = EXCLUDED.payload,
                selected_at = now()
            """,
            (person_id, WIKI_SOURCE, _wiki_key(profile), profile["name"], Json(payload)),
        )
        if "agent" in fields and profile.get("agent"):
            save_wiki_spells(conn, person_id, profile["agent"])
        conn.commit()


def save_sapphic(person_id: int, slug: str, fields: list[str]) -> None:
    try:
        profile = fetch_star(slug)
    except urllib.error.URLError as exc:
        raise ValueError("스타 페이지를 읽지 못했습니다") from exc
    payload = selected_payload(profile, fields)
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM person WHERE id = %s", (person_id,)).fetchone()
        if exists is None:
            raise ValueError("없는 배우입니다")
        taken = conn.execute(
            """
            SELECT person_id FROM person_source
            WHERE source = %s AND external_key = %s AND person_id <> %s
            """,
            (SOURCE, profile["slug"], person_id),
        ).fetchone()
        if taken:
            raise ValueError("이미 다른 배우에 연결된 스타 페이지입니다")
        conn.execute(
            """
            INSERT INTO person_source (person_id, source, external_key, display_name, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (person_id, source) DO UPDATE
            SET external_key = EXCLUDED.external_key,
                display_name = EXCLUDED.display_name,
                payload = EXCLUDED.payload,
                selected_at = now()
            """,
            (person_id, SOURCE, profile["slug"], profile["name"], Json(payload)),
        )
        if "company" in fields and isinstance(profile.get("company"), dict):
            save_sapphic_company(conn, person_id, profile["company"])
        ships = profile["ships"] if "ships" in fields and profile.get("ships") else []
        save_person_ships(conn, person_id, ships)
        conn.commit()


def linked_ships(person_id: int) -> list[dict]:
    with connect() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            """
            SELECT s.slug, s.name, s.image_url
            FROM person_ship ps
            JOIN ship s ON s.id = ps.ship_id
            WHERE ps.person_id = %s
            ORDER BY s.name
            """,
            (person_id,),
        ).fetchall()


def save_person_ships(conn, person_id: int, ships: list) -> None:
    conn.execute("DELETE FROM person_ship WHERE person_id = %s", (person_id,))
    for ship in ships:
        if not isinstance(ship, dict):
            continue
        slug = str(ship.get("slug") or "").strip()
        name = str(ship.get("name") or "").strip()
        if not slug or not name:
            continue
        image = ship.get("image_url")
        image = image.strip() if isinstance(image, str) and image.strip() else None
        row = conn.execute(
            """
            INSERT INTO ship (slug, name, image_url)
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                image_url = COALESCE(EXCLUDED.image_url, ship.image_url)
            RETURNING id
            """,
            (slug, name, image),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO person_ship (person_id, ship_id)
            VALUES (%s, %s)
            ON CONFLICT (person_id, ship_id) DO NOTHING
            """,
            (person_id, row[0]),
        )


def move_ships(conn) -> None:
    found = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'person'
          AND column_name = 'ships'
        """
    ).fetchone()
    if found is None:
        return
    rows = conn.execute("SELECT id, ships FROM person").fetchall()
    for person_id, ships in rows:
        if isinstance(ships, list) and ships:
            save_person_ships(conn, person_id, ships)
    conn.execute("ALTER TABLE person DROP COLUMN ships")
