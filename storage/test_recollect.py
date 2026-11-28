import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://glow:glow@127.0.0.1:5433/glow"
)

from app.api import apply_recollect
from app.collect import connect


def main() -> None:
    with connect() as conn:
        person_id = conn.execute(
            """
            INSERT INTO person (mdl_id, collect_status, socials)
            VALUES ('999000111', 'collected', %s::jsonb)
            RETURNING id
            """,
            ('[{"kind":"instagram","url":"https://instagram.com/x"}]',),
        ).fetchone()[0]
        other_id = conn.execute(
            """
            INSERT INTO person (mdl_id, collect_status)
            VALUES ('999000112', 'collected')
            RETURNING id
            """
        ).fetchone()[0]
        work_id = conn.execute(
            """
            INSERT INTO work (title, kind)
            VALUES ('recollect probe', 'drama')
            RETURNING id
            """
        ).fetchone()[0]
        company_id = conn.execute(
            """
            INSERT INTO company (name, name_key)
            VALUES ('recollect probe', 'recollect-probe')
            RETURNING id
            """
        ).fetchone()[0]
        own_ship = conn.execute(
            """
            INSERT INTO ship (slug, name)
            VALUES ('recollect-own', 'own')
            RETURNING id
            """
        ).fetchone()[0]
        shared_ship = conn.execute(
            """
            INSERT INTO ship (slug, name)
            VALUES ('recollect-shared', 'shared')
            RETURNING id
            """
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO person_work (person_id, work_id, role, character_name)
            VALUES (%s, %s, 'Main Role', 'Lead')
            """,
            (person_id, work_id),
        )
        conn.execute(
            """
            INSERT INTO person_source (person_id, source, external_key, payload)
            VALUES (%s, 'en_wikipedia', 'recollect-probe', '{}')
            """,
            (person_id,),
        )
        conn.execute(
            """
            INSERT INTO person_company (person_id, company_id)
            VALUES (%s, %s)
            """,
            (person_id, company_id),
        )
        conn.execute(
            "INSERT INTO person_ship (person_id, ship_id) VALUES (%s, %s), (%s, %s), (%s, %s)",
            (person_id, own_ship, person_id, shared_ship, other_id, shared_ship),
        )
        apply_recollect(
            conn,
            person_id,
            [{"work_id": work_id, "role": "Director", "character_name": None}],
        )
        socials = conn.execute(
            "SELECT socials FROM person WHERE id = %s", (person_id,)
        ).fetchone()[0]
        if socials != []:
            raise SystemExit(f"socials {socials}")
        sources = conn.execute(
            "SELECT count(*) FROM person_source WHERE person_id = %s", (person_id,)
        ).fetchone()[0]
        if sources != 0:
            raise SystemExit("source remains")
        agencies = conn.execute(
            "SELECT count(*) FROM person_company WHERE person_id = %s", (person_id,)
        ).fetchone()[0]
        if agencies != 0:
            raise SystemExit("agency link remains")
        company = conn.execute(
            "SELECT count(*) FROM company WHERE id = %s", (company_id,)
        ).fetchone()[0]
        if company != 1:
            raise SystemExit("company row deleted")
        work = conn.execute(
            "SELECT count(*) FROM work WHERE id = %s", (work_id,)
        ).fetchone()[0]
        if work != 1:
            raise SystemExit("work row deleted")
        roles = conn.execute(
            """
            SELECT role FROM person_work
            WHERE person_id = %s AND work_id = %s
            ORDER BY role
            """,
            (person_id, work_id),
        ).fetchall()
        if [row[0] for row in roles] != ["Director", "Main Role"]:
            raise SystemExit(f"roles {roles}")
        codes = conn.execute(
            """
            SELECT role_code FROM person_role
            WHERE person_id = %s AND role_code = 'd'
            """,
            (person_id,),
        ).fetchone()
        if codes is None:
            raise SystemExit("director role missing")
        own = conn.execute(
            "SELECT count(*) FROM ship WHERE id = %s", (own_ship,)
        ).fetchone()[0]
        if own != 0:
            raise SystemExit("orphan ship remains")
        shared = conn.execute(
            "SELECT count(*) FROM ship WHERE id = %s", (shared_ship,)
        ).fetchone()[0]
        if shared != 1:
            raise SystemExit("shared ship deleted")
        conn.rollback()
    print("ok")


if __name__ == "__main__":
    main()
