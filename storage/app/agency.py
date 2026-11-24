import re

import psycopg
from psycopg.types.json import Json

_RANGE = re.compile(r"\(([^)]*)\)\s*$")
_YEAR = re.compile(r"(\d{4})\s*[–—-]\s*(\d{4}|present)", re.I)
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_REF = re.compile(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", re.S)
_SLUG = re.compile(r"^[a-z0-9-]+$")


def name_key(name: str) -> str:
    text = name.casefold()
    text = re.sub(r"[^0-9a-z\uac00-\ud7a3\u0e00-\u0e7f]+", " ", text)
    return "_".join(text.split())


def parse_agent(text: str) -> list[dict]:
    spells = []
    seen: set[tuple] = set()
    lines = [line.strip().lstrip("*").strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    for line in lines:
        start = end = None
        period = None
        current = True
        name = line
        match = _RANGE.search(line)
        if match:
            years = _YEAR.search(match.group(1))
            if years:
                period = match.group(1).strip()
                start = int(years.group(1))
                token = years.group(2).lower()
                if token == "present":
                    current = True
                else:
                    end = int(token)
                    current = False
                name = line[: match.start()].strip()
        name = _plain(name)
        key = name_key(name)
        if not name or not key:
            continue
        marker = (key, start, end)
        if marker in seen:
            continue
        seen.add(marker)
        spells.append(
            {
                "name": name,
                "start_year": start,
                "end_year": end,
                "period_text": period,
                "is_current": current,
            }
        )
    return spells


def save_sapphic_company(
    conn: psycopg.Connection,
    person_id: int,
    company: dict,
) -> None:
    name = str(company.get("name") or "").strip()
    slug = str(company.get("slug") or "").strip().lower()
    if not name or not name_key(name) or not _SLUG.fullmatch(slug):
        return
    company_id = _upsert_company(conn, name, slug)
    conn.execute(
        """
        INSERT INTO company_type (company_id, org_type_id)
        SELECT %s, id FROM org_type WHERE name = '엔터테이먼트'
        ON CONFLICT DO NOTHING
        """,
        (company_id,),
    )
    conn.execute(
        """
        UPDATE person_company
        SET is_current = false
        WHERE person_id = %s AND company_id <> %s AND relation = 'agency'
          AND start_year IS NULL AND end_year IS NULL AND period_text IS NULL
        """,
        (person_id, company_id),
    )
    rows = _spells(conn, person_id, company_id)
    undated = [row for row in rows if row[1] is None and row[2] is None and row[3] is None]
    if undated:
        conn.execute(
            "UPDATE person_company SET is_current = true WHERE id = %s",
            (undated[0][0],),
        )
        return
    if rows:
        return
    _insert(conn, person_id, company_id, None, None, None, True)


def save_wiki_spells(conn: psycopg.Connection, person_id: int, spells: list[dict]) -> None:
    for spell in spells:
        if not name_key(spell["name"]):
            continue
        company_id = _upsert_company(conn, spell["name"], None)
        rows = _spells(conn, person_id, company_id)
        match = next((row for row in rows if row[1] == spell["start_year"]), None)
        if match is None:
            match = next((row for row in rows if row[1] is None and row[2] is None), None)
        if match:
            conn.execute(
                """
                UPDATE person_company
                SET start_year = %s, end_year = %s, period_text = %s, is_current = %s
                WHERE id = %s
                """,
                (
                    spell["start_year"],
                    spell["end_year"],
                    spell["period_text"],
                    spell["is_current"],
                    match[0],
                ),
            )
            continue
        _insert(
            conn,
            person_id,
            company_id,
            spell["start_year"],
            spell["end_year"],
            spell["period_text"],
            spell["is_current"],
        )


def backfill_sapphic(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        """
        SELECT person_id, payload
        FROM person_source
        WHERE source = 'sapphic_effect'
        """
    ).fetchall()
    for person_id, payload in rows:
        company = payload.get("company") if isinstance(payload, dict) else None
        if isinstance(company, dict):
            save_sapphic_company(conn, int(person_id), company)
    _fill_sapphic_pages(conn)


def _fill_sapphic_pages(conn: psycopg.Connection) -> None:
    from app.sapphic import fetch_star

    rows = conn.execute(
        """
        SELECT person_id, external_key, payload
        FROM person_source
        WHERE source = 'sapphic_effect'
        """
    ).fetchall()
    for person_id, slug, payload in rows:
        if not isinstance(payload, dict) or payload.get("biography"):
            continue
        try:
            profile = fetch_star(str(slug))
        except Exception:
            continue
        biography = profile.get("biography")
        if not biography:
            continue
        updated = dict(payload)
        updated["biography"] = biography
        conn.execute(
            """
            UPDATE person_source
            SET payload = %s
            WHERE person_id = %s AND source = 'sapphic_effect'
            """,
            (Json(updated), person_id),
        )


def _upsert_company(conn: psycopg.Connection, name: str, slug: str | None) -> int:
    key = name_key(name)
    if slug:
        row = conn.execute(
            "SELECT id FROM company WHERE sapphic_slug = %s",
            (slug,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE company SET name = %s, name_key = %s WHERE id = %s",
                (name, key, row[0]),
            )
            return int(row[0])
    row = conn.execute(
        "SELECT id, sapphic_slug FROM company WHERE name_key = %s ORDER BY id",
        (key,),
    ).fetchone()
    if row:
        if slug and not row[1]:
            conn.execute(
                "UPDATE company SET sapphic_slug = %s, name = %s WHERE id = %s",
                (slug, name, row[0]),
            )
        return int(row[0])
    created = conn.execute(
        """
        INSERT INTO company (name, name_key, sapphic_slug)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (name, key, slug),
    ).fetchone()
    return int(created[0])


def _spells(conn: psycopg.Connection, person_id: int, company_id: int) -> list[tuple]:
    return conn.execute(
        """
        SELECT id, start_year, end_year, period_text
        FROM person_company
        WHERE person_id = %s AND company_id = %s AND relation = 'agency'
        ORDER BY id
        """,
        (person_id, company_id),
    ).fetchall()


def _insert(
    conn: psycopg.Connection,
    person_id: int,
    company_id: int,
    start_year: int | None,
    end_year: int | None,
    period_text: str | None,
    is_current: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO person_company
            (person_id, company_id, relation, start_year, end_year, period_text, is_current)
        VALUES (%s, %s, 'agency', %s, %s, %s, %s)
        """,
        (person_id, company_id, start_year, end_year, period_text, is_current),
    )


def _plain(value: str) -> str:
    text = _REF.sub("", value)
    text = _LINK.sub(r"\1", text)
    text = re.sub(r"\{\{[^{}]+\}\}", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\s+", " ", text).strip(" *-")
    return text
