import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p/original"
NETWORK_TYPES = ("방송사",)
STUDIO_TYPES = ("제작사", "배급사")
PROVIDER_TYPE = "배급사"
OFFERS = {
    "flatrate": "유료 구독",
    "free": "Free",
    "ads": "광고",
    "rent": "대여",
    "buy": "구매",
}
COUNTRIES = ("KR", "TH")


def fill_person(person_id: int) -> None:
    from app.collect import connect

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT w.id
            FROM work w
            JOIN person_work pw ON pw.work_id = w.id
            WHERE pw.person_id = %s AND w.tmdb_id IS NULL
            ORDER BY w.id
            """,
            (person_id,),
        ).fetchall()
    for (work_id,) in rows:
        try:
            match_work(int(work_id))
        except Exception:
            continue


def match_work(work_id: int) -> None:
    from app.collect import connect

    with connect() as conn:
        work = conn.execute(
            "SELECT id, title, kind, year, tmdb_id FROM work WHERE id = %s",
            (work_id,),
        ).fetchone()
        if work is None or work[4] is not None:
            return
        kind = "movie" if work[2] == "movie" else "tv"
        found = search(kind, work[1], work[3])
        if found is None:
            return
        rows = providers(kind, found)
        _store(conn, work_id, found, kind, rows)
        enrich_companies(conn, work_id, kind, found)
        conn.commit()


def save_tmdb(work_id: int, raw_id: str, raw_kind: str) -> None:
    kind = (raw_kind or "").strip()
    if kind not in ("movie", "tv"):
        raise ValueError("movie 또는 tv")
    text = (raw_id or "").strip()
    if not re.fullmatch(r"\d+", text):
        raise ValueError("TMDB id가 아닙니다")
    tmdb_id = int(text)
    rows = providers(kind, tmdb_id)
    from app.collect import connect

    with connect() as conn:
        found = conn.execute("SELECT 1 FROM work WHERE id = %s", (work_id,)).fetchone()
        if found is None:
            raise ValueError("없는 작품입니다")
        _store(conn, work_id, tmdb_id, kind, rows)
        enrich_companies(conn, work_id, kind, tmdb_id)
        conn.commit()


def search(kind: str, title: str, year: int | None) -> int | None:
    if kind == "movie":
        params: dict[str, str] = {"query": title}
        if year is not None:
            params["year"] = str(year)
        data = _get("/search/movie", params)
    else:
        params = {"query": title}
        if year is not None:
            params["first_air_date_year"] = str(year)
        data = _get("/search/tv", params)
    results = data.get("results") if isinstance(data.get("results"), list) else []
    exact = None
    for item in results:
        if not isinstance(item, dict):
            continue
        names = (
            item.get("name"),
            item.get("title"),
            item.get("original_name"),
            item.get("original_title"),
        )
        if any(_same(title, name) for name in names if isinstance(name, str)):
            exact = item
            break
    chosen = exact
    if chosen is None and year is not None and results and isinstance(results[0], dict):
        chosen = results[0]
    if chosen is None or not isinstance(chosen.get("id"), int):
        return None
    return chosen["id"]


def providers(kind: str, tmdb_id: int) -> list[tuple[str, str, str, str | None, str | None]]:
    data = _get(f"/{kind}/{tmdb_id}/watch/providers", {})
    results = data.get("results") if isinstance(data.get("results"), dict) else {}
    rows: list[tuple[str, str, str, str | None, str | None]] = []
    seen: set[tuple[str, str, str]] = set()
    for country in COUNTRIES:
        block = results.get(country)
        if not isinstance(block, dict):
            continue
        link = block.get("link")
        url = link.strip() if isinstance(link, str) and link.strip().startswith(("http://", "https://")) else None
        for key, offer in OFFERS.items():
            items = block.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("provider_name")
                if not isinstance(name, str) or not name.strip():
                    continue
                row = (country, name.strip(), offer)
                if row in seen:
                    continue
                seen.add(row)
                rows.append((*row, url, _logo_url(item.get("logo_path"))))
    return rows


def enrich_companies(conn, work_id: int, kind: str, tmdb_id: int) -> None:
    data = _get(f"/{kind}/{tmdb_id}", {})
    conn.execute(
        "UPDATE work SET homepage = %s WHERE id = %s",
        (_http(data.get("homepage")), work_id),
    )
    networks = data.get("networks") if isinstance(data.get("networks"), list) else []
    studios = data.get("production_companies") if isinstance(data.get("production_companies"), list) else []
    companies = list(conn.execute("SELECT id, name, logo_url, homepage FROM company").fetchall())
    for item in networks:
        _fill_company(conn, companies, item, "network", NETWORK_TYPES)
    for item in studios:
        _fill_company(conn, companies, item, "company", STUDIO_TYPES)


def _fill_company(conn, companies, item: object, resource: str, types: tuple[str, ...]) -> None:
    if not isinstance(item, dict):
        return
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return
    hits = [row for row in companies if isinstance(row[1], str) and _same(row[1], name)]
    if not hits:
        return
    logo = _logo_url(item.get("logo_path"))
    home = None
    needs_logo = any(_blank(row[2]) for row in hits)
    needs_home = any(_blank(row[3]) for row in hits)
    if needs_home or (needs_logo and logo is None):
        found_logo, home = _profile(resource, item.get("id"))
        if logo is None:
            logo = found_logo
    for company_id, _name, old_logo, old_home in hits:
        _add_types(conn, company_id, types)
        if logo is not None and _blank(old_logo):
            conn.execute(
                """
                UPDATE company
                SET logo_url = %s
                WHERE id = %s AND (logo_url IS NULL OR btrim(logo_url) = '')
                """,
                (logo, company_id),
            )
            old_logo = logo
        if home is not None and _blank(old_home):
            conn.execute(
                """
                UPDATE company
                SET homepage = %s
                WHERE id = %s AND (homepage IS NULL OR btrim(homepage) = '')
                """,
                (home, company_id),
            )
            old_home = home
        for index, row in enumerate(companies):
            if row[0] == company_id:
                companies[index] = (company_id, row[1], old_logo, old_home)


def _add_types(conn, company_id: int, names: tuple[str, ...]) -> None:
    for name in names:
        conn.execute(
            """
            INSERT INTO company_type (company_id, org_type_id)
            SELECT %s, id FROM org_type WHERE name = %s
            ON CONFLICT DO NOTHING
            """,
            (company_id, name),
        )


def _profile(resource: str, raw_id: object) -> tuple[str | None, str | None]:
    if not isinstance(raw_id, int):
        return None, None
    try:
        data = _get(f"/{resource}/{raw_id}", {})
    except ValueError:
        return None, None
    home = data.get("homepage")
    if not isinstance(home, str) or not home.strip():
        home = None
    else:
        home = home.strip()
    return _logo_url(data.get("logo_path")), home


def _http(value: object) -> str | None:
    if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
        return value.strip()
    return None


def _logo_url(path: object) -> str | None:
    if isinstance(path, str) and path.startswith("/") and len(path) > 1:
        return IMAGE + path
    return None


def _blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _store(conn, work_id: int, tmdb_id: int, kind: str, rows: list[tuple[str, str, str, str | None, str | None]]) -> None:
    conn.execute(
        "UPDATE work SET tmdb_id = %s, tmdb_kind = %s WHERE id = %s",
        (tmdb_id, kind, work_id),
    )
    conn.execute("DELETE FROM work_provider WHERE work_id = %s", (work_id,))
    for country, name, offer, url, _logo in rows:
        conn.execute(
            """
            INSERT INTO work_provider (work_id, country, name, offer, url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (work_id, country, name, offer, url),
        )
    _save_provider_companies(conn, rows)


def _save_provider_companies(conn, rows: list[tuple[str, str, str, str | None, str | None]]) -> None:
    from app.collect import _upsert_company_name, name_key

    logos: dict[str, tuple[str, str | None]] = {}
    for _country, name, _offer, _url, logo in rows:
        key = name_key(name)
        if not key:
            continue
        current = logos.get(key)
        if current is None or (current[1] is None and logo is not None):
            logos[key] = (name, logo)
    for name, logo in logos.values():
        company_id = _upsert_company_name(conn, name)
        conn.execute(
            """
            INSERT INTO company_type (company_id, org_type_id)
            SELECT %s, id FROM org_type WHERE name = %s
            ON CONFLICT DO NOTHING
            """,
            (company_id, PROVIDER_TYPE),
        )
        if logo is None:
            continue
        conn.execute(
            """
            UPDATE company
            SET logo_url = %s
            WHERE id = %s AND (logo_url IS NULL OR btrim(logo_url) = '')
            """,
            (logo, company_id),
        )


def _get(path: str, params: dict[str, str]) -> dict:
    token = os.environ.get("tmdb_access_token_auth", "").strip()
    if not token:
        raise ValueError("TMDB 토큰이 없습니다")
    query = urllib.parse.urlencode(params)
    url = API + path
    if query:
        url = url + "?" + query
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise ValueError("TMDB 작품을 읽지 못했습니다") from exc
    except urllib.error.URLError as exc:
        raise ValueError("TMDB 작품을 읽지 못했습니다") from exc
    if not isinstance(data, dict):
        raise ValueError("TMDB 작품을 읽지 못했습니다")
    return data


def _same(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())
