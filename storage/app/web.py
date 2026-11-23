import html
import re
import urllib.error
from datetime import datetime
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.agency import backfill_sapphic, save_sapphic_company, save_wiki_spells
from app.collect import CREDIT_ROLES, apply_schema, collect_credits, collect_episodes, connect, drama_slug, fill_drama_details, move_credits, register, save_drama_detail
from app.fandom import SOURCE as FANDOM_SOURCE
from app.fandom import fetch_page, search as fandom_search, selected_payload as fandom_payload
from app.sapphic import SOURCE, fetch_star, search, selected_payload
from app.wikipedia import SOURCE as WIKI_SOURCE
from app.wikipedia import fetch_page as fetch_wiki
from app.wikipedia import gaps, search as wiki_search, selected_payload as wiki_payload

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
KIND_LABEL = {"drama": "드라마", "movie": "영화", "tv_show": "TV 쇼"}
CREDIT_LABEL = {
    "Screenwriter & Director": "작가·감독",
    "Director": "감독",
    "Screenwriter": "작가",
}
STATUS_CLASS = {
    "collected": "bg-emerald-100 text-emerald-800",
    "failed": "bg-red-100 text-red-800",
    "registered": "bg-amber-100 text-amber-800",
}


def serve(host: str, port: int) -> None:
    with connect() as conn:
        apply_schema(conn)
        backfill_sapphic(conn)
        move_credits(conn)
        move_ships(conn)
        conn.commit()
    Thread(target=fill_drama_details, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"http://{host}:{port}", flush=True)
    server.serve_forever()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path)
        person = re.fullmatch(r"/people/(\d+)", path.path)
        sapphic = re.fullmatch(r"/people/(\d+)/sapphic", path.path)
        fandom = re.fullmatch(r"/people/(\d+)/fandom", path.path)
        wiki = re.fullmatch(r"/people/(\d+)/wiki", path.path)
        work = re.fullmatch(r"/works/(\d+)", path.path)
        credit = re.fullmatch(r"/credits/(\d+)", path.path)
        company = re.fullmatch(r"/companies/(\d+)", path.path)
        if path.path in ("/", "/people"):
            self.respond(page("배우", people_body()))
            return
        if path.path == "/works":
            self.respond(page("작품", works_body()))
            return
        if path.path == "/credits":
            self.respond(page("작가·감독", credits_body()))
            return
        if path.path == "/companies":
            self.respond(page("소속사", companies_body()))
            return
        if path.path == "/register":
            error = parse_qs(path.query).get("error", [""])[0]
            self.respond(page("배우 등록", register_body(error)))
            return
        if sapphic:
            query = parse_qs(path.query)
            body = sapphic_search_body(
                int(sapphic.group(1)),
                query.get("q", [""])[0],
                query.get("error", [""])[0],
            )
            if body is None:
                self.respond(page("없는 배우", "<p class='text-sm text-stone-600'>없는 배우입니다.</p>"), 404)
                return
            self.respond(page("Sapphic Effect 검색", body))
            return
        if fandom:
            query = parse_qs(path.query)
            body = fandom_search_body(
                int(fandom.group(1)),
                query.get("q", [""])[0],
                query.get("error", [""])[0],
            )
            if body is None:
                self.respond(page("없는 배우", "<p class='text-sm text-stone-600'>없는 배우입니다.</p>"), 404)
                return
            self.respond(page("GMMTV Wiki 검색", body))
            return
        if wiki:
            query = parse_qs(path.query)
            body = wiki_search_body(
                int(wiki.group(1)),
                query.get("q", [""])[0],
                query.get("error", [""])[0],
            )
            if body is None:
                self.respond(page("없는 배우", "<p class='text-sm text-stone-600'>없는 배우입니다.</p>"), 404)
                return
            self.respond(page("영어 위키 검색", body))
            return
        if person:
            body = person_body(int(person.group(1)))
            if body is None:
                self.respond(page("없는 배우", "<p class='text-sm text-stone-600'>없는 배우입니다.</p>"), 404)
                return
            self.respond(page("배우", body))
            return
        if credit:
            body = credit_body(int(credit.group(1)))
            if body is None:
                self.respond(page("없는 작가·감독", "<p class='text-sm text-stone-600'>없는 작가·감독입니다.</p>"), 404)
                return
            self.respond(page("작가·감독", body))
            return
        if work:
            error = parse_qs(path.query).get("error", [""])[0]
            body = work_body(int(work.group(1)), error)
            if body is None:
                self.respond(page("없는 작품", "<p class='text-sm text-stone-600'>없는 작품입니다.</p>"), 404)
                return
            self.respond(page("작품", body))
            return
        if company:
            body = company_body(int(company.group(1)))
            if body is None:
                self.respond(page("없는 소속사", "<p class='text-sm text-stone-600'>없는 소속사입니다.</p>"), 404)
                return
            self.respond(page("소속사", body))
            return
        self.respond(page("없음", "<p class='text-sm text-stone-600'>없는 화면입니다.</p>"), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        sapphic = re.fullmatch(r"/people/(\d+)/sapphic", parsed.path)
        fandom = re.fullmatch(r"/people/(\d+)/fandom", parsed.path)
        wiki = re.fullmatch(r"/people/(\d+)/wiki", parsed.path)
        if wiki:
            person_id = int(wiki.group(1))
            title = form.get("title", [""])[0]
            try:
                save_wiki(person_id, title, form.get("fields", []))
            except ValueError as exc:
                self.redirect(f"/people/{person_id}/wiki?error=" + quote(str(exc)))
                return
            self.redirect(f"/people/{person_id}")
            return
        if fandom:
            person_id = int(fandom.group(1))
            title = form.get("title", [""])[0]
            try:
                save_fandom(person_id, title, form.get("fields", []))
            except ValueError as exc:
                self.redirect(f"/people/{person_id}/fandom?error=" + quote(str(exc)))
                return
            self.redirect(f"/people/{person_id}")
            return
        if sapphic:
            person_id = int(sapphic.group(1))
            slug = form.get("slug", [""])[0]
            try:
                save_sapphic(person_id, slug, form.get("fields", []))
            except ValueError as exc:
                self.redirect(f"/people/{person_id}/sapphic?error=" + quote(str(exc)))
                return
            self.redirect(f"/people/{person_id}")
            return
        if parsed.path != "/register":
            episode = re.fullmatch(r"/works/(\d+)/episodes", parsed.path)
            credit = re.fullmatch(r"/works/(\d+)/credits", parsed.path)
            if credit:
                work_id = int(credit.group(1))
                try:
                    collect_credits(work_id)
                except ValueError as exc:
                    self.redirect(f"/works/{work_id}?error=" + quote(str(exc)))
                    return
                self.redirect(f"/works/{work_id}")
                return
            if episode:
                work_id = int(episode.group(1))
                try:
                    collect_episodes(work_id)
                except ValueError as exc:
                    self.redirect(f"/works/{work_id}?error=" + quote(str(exc)))
                    return
                self.redirect(f"/works/{work_id}")
                return
            self.respond(page("없음", "<p class='text-sm text-stone-600'>없는 화면입니다.</p>"), 404)
            return
        raw_id = form.get("mdl_id", [""])[0]
        try:
            result = register(raw_id)
        except ValueError as exc:
            self.redirect("/register?error=" + quote(str(exc)))
            return
        self.redirect(f"/people/{result.person_id}")

    def respond(self, content: str, status: int = 200) -> None:
        body = content.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


def page(title: str, body: str) -> str:
    layout = (TEMPLATES / "layout.html").read_text()
    return layout.replace("{{title}}", esc(title)).replace("{{body}}", body)


def register_body(error: str) -> str:
    fragment = (TEMPLATES / "register.html").read_text()
    message = ""
    if error:
        message = f"<p class='mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700'>{esc(error)}</p>"
    return fragment.replace("{{error}}", message)


def people_body() -> str:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT p.id, p.mdl_id, p.name, p.native_name, p.nationality,
                   p.image_url, p.collect_status, p.collected_at,
                   (SELECT count(*) FROM person_work pw
                    WHERE pw.person_id = p.id AND NOT (pw.role = ANY(%s))) AS works
            FROM person p
            WHERE p.listed
            ORDER BY p.id DESC
            """,
            (list(CREDIT_ROLES),),
        ).fetchall()
    if not rows:
        return """
        <section class="rounded-lg border border-stone-200 bg-white p-6">
          <h1 class="text-xl font-semibold">배우 <span class="text-stone-400">0</span></h1>
          <p class="mt-2 text-sm text-stone-600">등록된 배우가 없습니다.</p>
          <a href="/register" class="mt-4 inline-block text-sm font-medium text-stone-900 underline">배우 등록</a>
        </section>
        """
    items = "\n".join(person_row(row) for row in rows)
    return f"""
    <section>
      <div class="mb-4 flex items-end justify-between">
        <h1 class="text-xl font-semibold">배우 <span class="text-stone-400">{len(rows)}</span></h1>
        <a href="/register" class="rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">배우 등록</a>
      </div>
      <div class="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
            <tr>
              <th class="px-4 py-3 font-medium"></th>
              <th class="px-4 py-3 font-medium">이름</th>
              <th class="px-4 py-3 font-medium">MDL id</th>
              <th class="px-4 py-3 font-medium">국적</th>
              <th class="px-4 py-3 font-medium">상태</th>
              <th class="px-4 py-3 font-medium">출연</th>
              <th class="px-4 py-3 font-medium">수집 시각</th>
            </tr>
          </thead>
          <tbody>{items}</tbody>
        </table>
      </div>
    </section>
    """


def person_row(row: dict) -> str:
    name = row["name"] or row["native_name"] or "이름 없음"
    native = row["native_name"] or ""
    sub = f"<span class='block text-xs text-stone-500'>{esc(native)}</span>" if native and native != name else ""
    thumb = ""
    if row["image_url"]:
        thumb = f"<img src='{esc(row['image_url'])}' alt='' class='h-12 w-9 rounded object-cover'>"
    return f"""
    <tr class="border-b border-stone-100 last:border-0 hover:bg-stone-50">
      <td class="px-4 py-2">{thumb}</td>
      <td class="px-4 py-3"><a class="font-medium" href="/people/{row['id']}">{esc(name)}</a>{sub}</td>
      <td class="px-4 py-3">{esc(row['mdl_id'])}</td>
      <td class="px-4 py-3">{esc(row['nationality'] or '')}</td>
      <td class="px-4 py-3">{status_badge(row['collect_status'])}</td>
      <td class="px-4 py-3">{int(row['works'])}</td>
      <td class="px-4 py-3 text-stone-500">{esc(stamp(row['collected_at']))}</td>
    </tr>
    """


def person_body(person_id: int) -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute("SELECT * FROM person WHERE id = %s", (person_id,)).fetchone()
        if person is None:
            return None
        sources = conn.execute(
            """
            SELECT source, display_name, external_key, payload, selected_at
            FROM person_source
            WHERE person_id = %s
            """,
            (person_id,),
        ).fetchall()
        by_source = {row["source"]: row for row in sources}
        source = by_source.get(SOURCE)
        fandom = by_source.get(FANDOM_SOURCE)
        wiki = by_source.get(WIKI_SOURCE)
        works = conn.execute(
            """
            SELECT w.id, w.title, w.kind, w.year, w.episodes, w.rating, w.mdl_id,
                   pw.role, pw.character_name
            FROM person_work pw
            JOIN work w ON w.id = pw.work_id
            WHERE pw.person_id = %s AND NOT (pw.role = ANY(%s))
            ORDER BY w.year DESC NULLS LAST, w.title
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchall()
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
    image = ""
    if person["image_url"]:
        image = f"<img src='{esc(person['image_url'])}' alt='' class='h-44 w-32 rounded-md object-cover'>"
    aliases = person["also_known_as"] or []
    alias_text = ", ".join(aliases)
    error = ""
    if person["collect_error"]:
        error = f"<p class='mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700'>{esc(person['collect_error'])}</p>"
    work_rows = "\n".join(work_row(row) for row in works) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='6'>출연작이 없습니다.</td></tr>
    """
    return f"""
    <a href="/people" class="text-sm text-stone-500 hover:text-stone-900">배우</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex gap-5">
        {image}
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-2xl font-semibold">{esc(person['name'] or '이름 없음')}</h1>
            {status_badge(person['collect_status'])}
          </div>
          <p class="mt-1 text-stone-600">{esc(person['native_name'] or '')}</p>
          {source_line(person)}
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {meta('활동명', person['stage_name'])}
            {meta('MDL id', person['mdl_id'])}
            {meta('국적', person['nationality'])}
            {meta('성별', person['gender'])}
            {meta('생일', person['born_text'])}
            {meta('다른 이름', alias_text)}
          </dl>
          {error}
        </div>
      </div>
    </section>
    {affiliation_block(affiliations)}
    {sapphic_saved(person, source)}
    {fandom_saved(person, source, fandom)}
    {wiki_saved(person, source, fandom, wiki)}
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <div class="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <h2 class="text-sm font-semibold">출연작 {len(works)}</h2>
        <p class="text-xs text-stone-500">MyDramaList 인물 응답의 필모그래피</p>
      </div>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium">제목</th>
            <th class="px-4 py-3 font-medium">종류</th>
            <th class="px-4 py-3 font-medium">연도</th>
            <th class="px-4 py-3 font-medium">구분</th>
            <th class="px-4 py-3 font-medium">배역</th>
            <th class="px-4 py-3 font-medium">평점</th>
          </tr>
        </thead>
        <tbody>{work_rows}</tbody>
      </table>
    </section>
    """


def work_row(row: dict) -> str:
    rating = "" if row["rating"] is None else str(row["rating"])
    year = "" if row["year"] is None else str(row["year"])
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-3"><a class="font-medium" href="/works/{row['id']}">{esc(row['title'])}</a></td>
      <td class="px-4 py-3">{esc(KIND_LABEL.get(row['kind'], row['kind']))}</td>
      <td class="px-4 py-3">{esc(year)}</td>
      <td class="px-4 py-3">{esc(row['role'] or '')}</td>
      <td class="px-4 py-3">{esc(row['character_name'] or '')}</td>
      <td class="px-4 py-3">{esc(rating)}</td>
    </tr>
    """


def works_body() -> str:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT w.id, w.title, w.kind, w.year, w.episodes, w.rating, w.image_url, w.tags,
                   (SELECT count(*) FROM person_work pw
                    WHERE pw.work_id = w.id AND NOT (pw.role = ANY(%s))) AS cast_count
            FROM work w
            ORDER BY w.year DESC NULLS LAST, w.title
            """,
            (list(CREDIT_ROLES),),
        ).fetchall()
    if not rows:
        return """
        <section class="rounded-lg border border-stone-200 bg-white p-6">
          <h1 class="text-xl font-semibold">작품</h1>
          <p class="mt-2 text-sm text-stone-600">수집된 작품이 없습니다.</p>
        </section>
        """
    items = "\n".join(work_list_row(row) for row in rows)
    return f"""
    <section>
      <h1 class="mb-4 text-xl font-semibold">작품</h1>
      <div class="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
            <tr>
              <th class="px-4 py-3 font-medium"></th>
              <th class="px-4 py-3 font-medium">제목</th>
              <th class="px-4 py-3 font-medium">종류</th>
              <th class="px-4 py-3 font-medium">연도</th>
              <th class="px-4 py-3 font-medium">에피소드</th>
              <th class="px-4 py-3 font-medium">평점</th>
              <th class="px-4 py-3 font-medium">출연</th>
            </tr>
          </thead>
          <tbody>{items}</tbody>
        </table>
      </div>
    </section>
    """


def work_list_row(row: dict) -> str:
    rating = "" if row["rating"] is None else str(row["rating"])
    year = "" if row["year"] is None else str(row["year"])
    episodes = "" if row["episodes"] is None else str(row["episodes"])
    thumb = ""
    if row["image_url"]:
        thumb = f"<img src='{esc(row['image_url'])}' alt='' class='h-12 w-9 rounded object-cover'>"
    return f"""
    <tr class="border-b border-stone-100 last:border-0 hover:bg-stone-50">
      <td class="px-4 py-2">{thumb}</td>
      <td class="px-4 py-3">
        <a class="font-medium" href="/works/{row['id']}">{esc(row['title'])}</a>
        {pair_tags(row['tags'])}
      </td>
      <td class="px-4 py-3">{esc(KIND_LABEL.get(row['kind'], row['kind']))}</td>
      <td class="px-4 py-3">{esc(year)}</td>
      <td class="px-4 py-3">{esc(episodes)}</td>
      <td class="px-4 py-3">{esc(rating)}</td>
      <td class="px-4 py-3">{int(row['cast_count'])}</td>
    </tr>
    """


PAIR_TAGS = (
    ("Lesbian Romance", "GL"),
    ("Gay Romance", "BL"),
    ("Gay Male Lead", "BL"),
)


def pair_tags(tags: object) -> str:
    values = set(tags) if isinstance(tags, (list, tuple)) else set()
    labels = []
    for source, label in PAIR_TAGS:
        if source in values and label not in labels:
            labels.append(label)
    return "".join(
        f"<span class='ml-2 rounded-full bg-stone-100 px-2 py-0.5 text-xs font-medium'>{label}</span>"
        for label in labels
    )


def credit_labels(roles: object) -> str:
    order = {role: index for index, role in enumerate(CREDIT_ROLES)}
    values = {role for role in (roles if isinstance(roles, (list, tuple)) else []) if isinstance(role, str)}
    if values & {"Screenwriter", "Screenwriter & Director"} and values & {"Director", "Screenwriter & Director"}:
        return "작가·감독"
    picked = sorted(values, key=lambda role: order.get(role, len(order)))
    return ", ".join(CREDIT_LABEL.get(role, role) for role in picked)


def credits_body() -> str:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.native_name, p.nationality, p.image_url,
                   array_agg(DISTINCT pw.role) AS roles,
                   count(DISTINCT pw.work_id) AS works
            FROM person p
            JOIN person_work pw ON pw.person_id = p.id
            WHERE pw.role = ANY(%s)
            GROUP BY p.id
            ORDER BY p.name
            """,
            (list(CREDIT_ROLES),),
        ).fetchall()
    if not rows:
        return """
        <section class="rounded-lg border border-stone-200 bg-white p-6">
          <h1 class="text-xl font-semibold">작가·감독</h1>
          <p class="mt-2 text-sm text-stone-600">수집된 작가·감독이 없습니다.</p>
        </section>
        """
    items = "\n".join(credit_list_row(row) for row in rows)
    return f"""
    <section>
      <h1 class="mb-4 text-xl font-semibold">작가·감독</h1>
      <div class="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
            <tr>
              <th class="px-4 py-3 font-medium"></th>
              <th class="px-4 py-3 font-medium">이름</th>
              <th class="px-4 py-3 font-medium">역할</th>
              <th class="px-4 py-3 font-medium">국적</th>
              <th class="px-4 py-3 font-medium">작품</th>
            </tr>
          </thead>
          <tbody>{items}</tbody>
        </table>
      </div>
    </section>
    """


def credit_list_row(row: dict) -> str:
    thumb = ""
    if row["image_url"]:
        thumb = f"<img src='{esc(row['image_url'])}' alt='' class='h-12 w-9 rounded object-cover'>"
    native = f"<span class='block text-xs text-stone-500'>{esc(row['native_name'])}</span>" if row["native_name"] else ""
    return f"""
    <tr class="border-b border-stone-100 last:border-0 hover:bg-stone-50">
      <td class="px-4 py-2">{thumb}</td>
      <td class="px-4 py-3"><a class="font-medium" href="/credits/{row['id']}">{esc(row['name'] or '이름 없음')}</a>{native}</td>
      <td class="px-4 py-3">{esc(credit_labels(row['roles']))}</td>
      <td class="px-4 py-3">{esc(row['nationality'] or '')}</td>
      <td class="px-4 py-3">{int(row['works'])}</td>
    </tr>
    """


def credit_body(person_id: int) -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            """
            SELECT p.*
            FROM person p
            WHERE p.id = %s
              AND EXISTS (
                SELECT 1 FROM person_work pw
                WHERE pw.person_id = p.id AND pw.role = ANY(%s)
              )
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchone()
        if person is None:
            return None
        works = conn.execute(
            """
            SELECT w.id, w.title, w.kind, w.year, pw.role
            FROM person_work pw
            JOIN work w ON w.id = pw.work_id
            WHERE pw.person_id = %s AND pw.role = ANY(%s)
            ORDER BY w.year DESC NULLS LAST, w.title
            """,
            (person_id, list(CREDIT_ROLES)),
        ).fetchall()
    image = ""
    if person["image_url"]:
        image = f"<img src='{esc(person['image_url'])}' alt='' class='h-44 w-32 rounded-md object-cover'>"
    aliases = ", ".join(person["also_known_as"] or [])
    work_rows = "\n".join(credit_work_row(row) for row in works) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='4'>연결된 작품이 없습니다.</td></tr>
    """
    return f"""
    <a href="/credits" class="text-sm text-stone-500 hover:text-stone-900">작가·감독</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex gap-5">
        {image}
        <div>
          <h1 class="text-2xl font-semibold">{esc(person['name'] or '이름 없음')}</h1>
          <p class="mt-1 text-stone-600">{esc(person['native_name'] or '')}</p>
          {source_line(person)}
          <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {meta('활동명', person['stage_name'])}
            {meta('MDL id', person['mdl_id'])}
            {meta('국적', person['nationality'])}
            {meta('성별', person['gender'])}
            {meta('생일', person['born_text'])}
            {meta('다른 이름', aliases)}
          </dl>
        </div>
      </div>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <h2 class="border-b border-stone-200 px-4 py-3 text-sm font-semibold">작품 {len(works)}</h2>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium">제목</th>
            <th class="px-4 py-3 font-medium">종류</th>
            <th class="px-4 py-3 font-medium">연도</th>
            <th class="px-4 py-3 font-medium">역할</th>
          </tr>
        </thead>
        <tbody>{work_rows}</tbody>
      </table>
    </section>
    """


def credit_work_row(row: dict) -> str:
    year = "" if row["year"] is None else str(row["year"])
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-3"><a class="font-medium" href="/works/{row['id']}">{esc(row['title'])}</a></td>
      <td class="px-4 py-3">{esc(KIND_LABEL.get(row['kind'], row['kind']))}</td>
      <td class="px-4 py-3">{esc(year)}</td>
      <td class="px-4 py-3">{esc(CREDIT_LABEL.get(row['role'], row['role']))}</td>
    </tr>
    """


def work_body(work_id: int, error_text: str = "") -> str | None:
    save_drama_detail(work_id)
    with connect() as conn:
        conn.row_factory = dict_row
        work = conn.execute("SELECT * FROM work WHERE id = %s", (work_id,)).fetchone()
        if work is None:
            return None
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
    rating = "" if work["rating"] is None else str(work["rating"])
    year = "" if work["year"] is None else str(work["year"])
    episode_count = "" if work["episodes"] is None else str(work["episodes"])
    cast_rows = "\n".join(cast_row(row) for row in cast) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='3'>출연 배우가 없습니다.</td></tr>
    """
    order = {role: index for index, role in enumerate(CREDIT_ROLES)}
    credits.sort(key=lambda row: (order.get(row["role"], len(order)), row["name"] or ""))
    credit_rows = "\n".join(credit_row(row) for row in credits) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='3'>가져온 작가·감독이 없습니다.</td></tr>
    """
    episode_rows = "\n".join(episode_row(row) for row in episodes) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='6'>가져온 에피소드가 없습니다.</td></tr>
    """
    poster = ""
    if work["image_url"]:
        poster = f"<img src='{esc(work['image_url'])}' alt='' class='h-44 w-32 rounded-md object-cover'>"
    error = ""
    if error_text:
        error = f"<p class='mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700'>{esc(error_text)}</p>"
    return f"""
    <a href="/works" class="text-sm text-stone-500 hover:text-stone-900">작품</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex gap-5">
        {poster}
        <div class="min-w-0 flex-1">
      <h1 class="text-2xl font-semibold">{esc(work['title'])}</h1>
      <p class="mt-2 text-sm text-stone-500">원제</p>
      <p class="text-lg">{esc(work['native_title'] or '없음')}</p>
      <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {meta('종류', KIND_LABEL.get(work['kind'], work['kind']))}
        {meta('연도', year)}
        {meta('회차', episode_count)}
        {meta('평점', rating)}
        {meta('MDL id', work['mdl_id'])}
      </dl>
      {tags_block(work['tags'])}
      {work_source_line(work)}
      {synopsis_block(work['synopsis'])}
      {error}
      <form method="post" action="/works/{work_id}/episodes" class="mt-4">
        <button class="rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">에피소드 가져오기</button>
      </form>
        </div>
      </div>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <div class="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <h2 class="text-sm font-semibold">작가·감독 {len(credits)}</h2>
        <form method="post" action="/works/{work_id}/credits">
          <button class="rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">작가·감독 가져오기</button>
        </form>
      </div>
      <p class="border-b border-stone-200 px-4 py-2 text-xs text-stone-500">kuryana /v2/dramas/{{slug}}/cast · /v2/people/{{id}}</p>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium"></th>
            <th class="px-4 py-3 font-medium">이름</th>
            <th class="px-4 py-3 font-medium">역할</th>
          </tr>
        </thead>
        <tbody>{credit_rows}</tbody>
      </table>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <h2 class="border-b border-stone-200 px-4 py-3 text-sm font-semibold">에피소드 {len(episodes)}</h2>
      <p class="border-b border-stone-200 px-4 py-2 text-xs text-stone-500">kuryana /v2/dramas/{{slug}}/episodes</p>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium"></th>
            <th class="px-4 py-3 font-medium">화</th>
            <th class="px-4 py-3 font-medium">제목</th>
            <th class="px-4 py-3 font-medium">방영</th>
            <th class="px-4 py-3 font-medium">평점</th>
            <th class="px-4 py-3 font-medium">설명</th>
          </tr>
        </thead>
        <tbody>{episode_rows}</tbody>
      </table>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <h2 class="border-b border-stone-200 px-4 py-3 text-sm font-semibold">출연 {len(cast)}</h2>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium">배우</th>
            <th class="px-4 py-3 font-medium">구분</th>
            <th class="px-4 py-3 font-medium">배역</th>
          </tr>
        </thead>
        <tbody>{cast_rows}</tbody>
      </table>
    </section>
    """


def credit_row(row: dict) -> str:
    thumb = ""
    if row["image_url"]:
        thumb = f"<img src='{esc(row['image_url'])}' alt='' class='h-12 w-9 rounded object-cover'>"
    native = f"<span class='block text-xs text-stone-500'>{esc(row['native_name'])}</span>" if row["native_name"] else ""
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-2">{thumb}</td>
      <td class="px-4 py-3"><a class="font-medium" href="/credits/{row['id']}">{esc(row['name'] or '')}</a>{native}</td>
      <td class="px-4 py-3">{esc(CREDIT_LABEL.get(row['role'], row['role']))}</td>
    </tr>
    """


def episode_row(row: dict) -> str:
    rating = "" if row["rating"] is None else str(row["rating"])
    thumb = ""
    if row["image_url"]:
        thumb = f"<img src='{esc(row['image_url'])}' alt='' class='h-12 w-20 rounded object-cover'>"
    title = esc(row["title"] or "")
    if row["mdl_url"]:
        title = f"<a class='underline' href='{esc(row['mdl_url'])}' target='_blank' rel='noreferrer'>{title}</a>"
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-2">{thumb}</td>
      <td class="px-4 py-3">{row['number']}</td>
      <td class="px-4 py-3">{title}</td>
      <td class="px-4 py-3">{esc(row['air_date'] or '')}</td>
      <td class="px-4 py-3">{esc(rating)}</td>
      <td class="px-4 py-3 max-w-md">{esc(row['summary'] or '')}</td>
    </tr>
    """


def cast_row(row: dict) -> str:
    name = row["name"] or row["native_name"] or "이름 없음"
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-3"><a class="font-medium" href="/people/{row['id']}">{esc(name)}</a></td>
      <td class="px-4 py-3">{esc(row['role'] or '')}</td>
      <td class="px-4 py-3">{esc(row['character_name'] or '')}</td>
    </tr>
    """


def companies_body() -> str:
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.mdl_id, c.match_status,
                   (SELECT count(*) FROM person_company pc WHERE pc.company_id = c.id) AS members
            FROM company c
            ORDER BY c.name
            """
        ).fetchall()
    if not rows:
        return """
        <section class="rounded-lg border border-stone-200 bg-white p-6">
          <h1 class="text-xl font-semibold">소속사</h1>
          <p class="mt-2 text-sm text-stone-600">등록된 소속사가 없습니다.</p>
        </section>
        """
    items = "\n".join(company_row(row) for row in rows)
    return f"""
    <section>
      <h1 class="mb-4 text-xl font-semibold">소속사</h1>
      <div class="overflow-hidden rounded-lg border border-stone-200 bg-white">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
            <tr>
              <th class="px-4 py-3 font-medium">이름</th>
              <th class="px-4 py-3 font-medium">MDL id</th>
              <th class="px-4 py-3 font-medium">매칭</th>
              <th class="px-4 py-3 font-medium">소속 배우</th>
            </tr>
          </thead>
          <tbody>{items}</tbody>
        </table>
      </div>
    </section>
    """


def company_row(row: dict) -> str:
    return f"""
    <tr class="border-b border-stone-100 last:border-0 hover:bg-stone-50">
      <td class="px-4 py-3"><a class="font-medium" href="/companies/{row['id']}">{esc(row['name'])}</a></td>
      <td class="px-4 py-3">{esc(row['mdl_id'] or '')}</td>
      <td class="px-4 py-3">{esc(row['match_status'])}</td>
      <td class="px-4 py-3">{int(row['members'])}</td>
    </tr>
    """


def company_body(company_id: int) -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        company = conn.execute("SELECT * FROM company WHERE id = %s", (company_id,)).fetchone()
        if company is None:
            return None
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
    people_rows = "\n".join(member_row(row) for row in people) or """
      <tr><td class='px-4 py-6 text-stone-500' colspan='3'>소속 배우가 없습니다.</td></tr>
    """
    return f"""
    <a href="/companies" class="text-sm text-stone-500 hover:text-stone-900">소속사</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <h1 class="text-2xl font-semibold">{esc(company['name'])}</h1>
      <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {meta('MDL id', company['mdl_id'])}
        {meta('매칭', company['match_status'])}
      </dl>
    </section>
    <section class="mt-6 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <h2 class="border-b border-stone-200 px-4 py-3 text-sm font-semibold">소속 배우 {len(people)}</h2>
      <table class="w-full text-left text-sm">
        <thead class="border-b border-stone-200 bg-stone-50 text-stone-500">
          <tr>
            <th class="px-4 py-3 font-medium">배우</th>
            <th class="px-4 py-3 font-medium">기간</th>
            <th class="px-4 py-3 font-medium">현재</th>
          </tr>
        </thead>
        <tbody>{people_rows}</tbody>
      </table>
    </section>
    """


def member_row(row: dict) -> str:
    name = row["name"] or row["native_name"] or "이름 없음"
    current = "현재" if row["is_current"] else ""
    return f"""
    <tr class="border-b border-stone-100 last:border-0">
      <td class="px-4 py-3"><a class="font-medium" href="/people/{row['id']}">{esc(name)}</a></td>
      <td class="px-4 py-3">{esc(row['period_text'] or '')}</td>
      <td class="px-4 py-3">{current}</td>
    </tr>
    """


def affiliation_block(rows: list[dict]) -> str:
    if not rows:
        return ""
    current = ", ".join(
        f"<a class='underline' href='/companies/{row['company_id']}'>{esc(row['name'])}</a>"
        for row in rows
        if row["is_current"]
    )
    history = []
    for row in rows:
        if row["is_current"] and not row["period_text"]:
            continue
        label = esc(row["name"])
        if row["period_text"]:
            label += f" {esc(row['period_text'])}"
        if row["is_current"]:
            label += " 현재"
        history.append(
            f"<li><a class='underline' href='/companies/{row['company_id']}'>{label}</a></li>"
        )
    history_html = ""
    if history:
        history_html = f"<ul class='mt-3 list-disc pl-5 text-sm'>{''.join(history)}</ul>"
    return f"""
    <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
      <h2 class="text-sm font-semibold">소속</h2>
      <p class="mt-2 text-sm">현재 {current or "없음"}</p>
      {history_html}
    </section>
    """


def is_gmmtv(source: dict | None) -> bool:
    if source is None or not isinstance(source["payload"], dict):
        return False
    company = source["payload"].get("company") or {}
    if not isinstance(company, dict):
        return False
    name = str(company.get("name") or "").strip().lower()
    slug = str(company.get("slug") or "").strip().lower()
    return name == "gmmtv" or slug == "gmmtv"


def fandom_saved(person: dict, sapphic: dict | None, source: dict | None) -> str:
    if source is None and not is_gmmtv(sapphic):
        return ""
    query = quote(person["stage_name"] or person["name"] or person["mdl_id"])
    link = ""
    if is_gmmtv(sapphic):
        link = f"<a class='text-sm font-medium underline' href='/people/{person['id']}/fandom?q={query}'>위키에서 고르기</a>"
    if source is None:
        return f"""
        <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
          <h2 class="text-sm font-semibold">GMMTV Wiki</h2>
          <p class="mt-2 text-sm text-stone-600">선택한 위키 정보가 없습니다.</p>
          <p class="mt-3">{link}</p>
        </section>
        """
    payload = source["payload"] if isinstance(source["payload"], dict) else {}
    socials = payload.get("socials") or []
    social_html = "".join(
        f"<li><a class='underline' href='{esc(item['url'])}' target='_blank' rel='noreferrer'>{esc(item.get('kind') or item['url'])}</a></li>"
        for item in socials
        if isinstance(item, dict) and item.get("url")
    )
    image = ""
    if payload.get("image_url"):
        image = f"<img src='{esc(payload['image_url'])}' alt='' class='h-24 w-20 rounded-md object-cover'>"
    return f"""
    <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">GMMTV Wiki</h2>
          <p class="mt-1 text-sm text-stone-600">
            출처 <a class="font-medium text-stone-900 underline" href="{esc(payload.get('url') or '')}" target="_blank" rel="noreferrer">{esc(source['display_name'] or source['external_key'])}</a>
            · CC-BY-SA · {esc(stamp(source['selected_at']))}
          </p>
        </div>
        {link}
      </div>
      <div class="mt-4 flex gap-4">
        {image}
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {meta('본명', payload.get('birth_name'))}
        {meta('닉네임', payload.get('nickname'))}
        {meta('태국어 이름', payload.get('native_name'))}
        {meta('생일', payload.get('birthday'))}
        {meta('출생지', payload.get('birth_place'))}
        {meta('키', payload.get('height'))}
        {meta('몸무게', payload.get('weight'))}
        {meta('활동', payload.get('years_active'))}
      </dl>
      </div>
      {prose_block(payload.get('early_life'))}
      {f"<ul class='mt-3 list-disc pl-5 text-sm'>{social_html}</ul>" if social_html else ""}
    </section>
    """


def fandom_search_body(person_id: int, query: str, error_text: str = "") -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            "SELECT id, name, stage_name, mdl_id FROM person WHERE id = %s",
            (person_id,),
        ).fetchone()
        sapphic = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, SOURCE),
        ).fetchone()
    if person is None:
        return None
    if not is_gmmtv(sapphic):
        return """
        <p class="text-sm text-stone-600">Sapphic Effect 소속사가 GMMTV일 때만 GMMTV Wiki를 찾는다.</p>
        """
    active_query = query or person["stage_name"] or person["name"] or ""
    error = f"<p class='mt-4 text-sm text-red-700'>{esc(error_text)}</p>" if error_text else ""
    cards = ""
    if active_query.strip():
        try:
            profiles = fandom_search(active_query)
        except (urllib.error.URLError, TimeoutError) as exc:
            profiles = []
            error = f"<p class='mt-4 text-sm text-red-700'>{esc(exc)}</p>"
        if not profiles and not error:
            error = "<p class='mt-4 text-sm text-stone-600'>맞는 위키 문서가 없습니다.</p>"
        cards = "\n".join(fandom_card(person_id, profile) for profile in profiles)
    return f"""
    <a href="/people/{person_id}" class="text-sm text-stone-500 hover:text-stone-900">배우</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <h1 class="text-xl font-semibold">GMMTV Wiki 검색</h1>
      <p class="mt-2 text-sm text-stone-600">고른 항목만 이 배우의 GMMTV Wiki 출처로 저장한다.</p>
      <form method="get" action="/people/{person_id}/fandom" class="mt-4 flex gap-2">
        <input name="q" value="{esc(active_query)}" class="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
        <button class="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white">검색</button>
      </form>
      {error}
    </section>
    <div class="mt-4 space-y-4">{cards}</div>
    """


def fandom_card(person_id: int, profile: dict) -> str:
    checks = []
    labels = (
        ("birth_name", "본명"),
        ("nickname", "닉네임"),
        ("native_name", "태국어 이름"),
        ("birthday", "생일"),
        ("birth_place", "출생지"),
        ("height", "키"),
        ("weight", "몸무게"),
        ("years_active", "활동"),
    )
    for key, label in labels:
        if profile.get(key):
            checks.append((key, f"{label} {profile[key]}"))
    if profile.get("image_url"):
        checks.append(("image", "프로필 이미지"))
    if profile["socials"]:
        checks.append(("socials", f"SNS {len(profile['socials'])}개"))
    if profile["early_life"]:
        checks.append(("early_life", "Early Life"))
    boxes = "".join(
        f"""<label class="flex items-center gap-2 text-sm">
          <input type="checkbox" name="fields" value="{esc(key)}" checked>
          {esc(label)}
        </label>"""
        for key, label in checks
    )
    return f"""
    <form method="post" action="/people/{person_id}/fandom" class="rounded-lg border border-stone-200 bg-white p-5">
      <input type="hidden" name="title" value="{esc(profile['title'])}">
      <h2 class="text-lg font-semibold">{esc(profile['name'])}</h2>
      <a class="text-sm text-stone-500 underline" href="{esc(profile['url'])}" target="_blank" rel="noreferrer">{esc(profile['title'])}</a>
      {f"<img src='{esc(profile['image_url'])}' alt='' class='mt-3 h-24 w-20 rounded-md object-cover'>" if profile.get("image_url") else ""}
      <div class="mt-3 space-y-2">{boxes}</div>
      {prose_block(profile["early_life"])}
      <button class="mt-4 rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">이 정보 넣기</button>
    </form>
    """


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


WIKI_LABELS = (
    ("image", "프로필 이미지"),
    ("birth_name", "본명"),
    ("native_name", "원어 이름"),
    ("birthday", "생일"),
    ("birth_place", "출생지"),
    ("height", "키"),
    ("education", "학력"),
    ("years_active", "활동 기간"),
    ("agent", "소속사"),
    ("career", "Career"),
    ("fashion", "Fashion"),
    ("ambassadorship", "Ambassadorship"),
    ("accolades", "Accolades"),
)


def wiki_saved(person: dict, sapphic: dict | None, fandom: dict | None, source: dict | None) -> str:
    query = quote(person["name"] or person["stage_name"] or person["mdl_id"])
    link = f"<a class='text-sm font-medium underline' href='/people/{person['id']}/wiki?q={query}'>위키에서 고르기</a>"
    if source is None:
        hint = "GMMTV Wiki에 없는 항목만 고른다." if is_gmmtv(sapphic) else "선택한 위키 정보가 없습니다."
        return f"""
        <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
          <h2 class="text-sm font-semibold">영어 위키</h2>
          <p class="mt-2 text-sm text-stone-600">{hint}</p>
          <p class="mt-3">{link}</p>
        </section>
        """
    payload = source["payload"] if isinstance(source["payload"], dict) else {}
    image = ""
    if payload.get("image_url"):
        image = f"<img src='{esc(payload['image_url'])}' alt='' class='h-24 w-20 rounded-md object-cover'>"
    blocks = []
    for key, label in (("career", "Career"), ("fashion", "Fashion"), ("ambassadorship", "Ambassadorship"), ("accolades", "Accolades")):
        if payload.get(key):
            blocks.append(f"<h3 class='mt-4 text-sm font-medium'>{label}</h3>{prose_block(payload[key])}")
    return f"""
    <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">영어 위키</h2>
          <p class="mt-1 text-sm text-stone-600">
            출처 <a class="font-medium text-stone-900 underline" href="{esc(payload.get('url') or '')}" target="_blank" rel="noreferrer">{esc(source['display_name'] or source['external_key'])}</a>
            · CC-BY-SA · {esc(stamp(source['selected_at']))}
          </p>
        </div>
        {link}
      </div>
      <div class="mt-4 flex gap-4">
        {image}
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {meta('본명', payload.get('birth_name'))}
        {meta('원어 이름', payload.get('native_name'))}
        {meta('생일', payload.get('birthday'))}
        {meta('출생지', payload.get('birth_place'))}
        {meta('키', payload.get('height'))}
        {meta('학력', payload.get('education'))}
        {meta('활동 기간', payload.get('years_active'))}
      </dl>
      </div>
      {''.join(blocks)}
    </section>
    """


def wiki_search_body(person_id: int, query: str, error_text: str = "") -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            "SELECT id, name, stage_name, mdl_id FROM person WHERE id = %s",
            (person_id,),
        ).fetchone()
        sapphic = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, SOURCE),
        ).fetchone()
        fandom = conn.execute(
            "SELECT payload FROM person_source WHERE person_id = %s AND source = %s",
            (person_id, FANDOM_SOURCE),
        ).fetchone()
    if person is None:
        return None
    gmmtv = is_gmmtv(sapphic)
    allowed = gaps(fandom["payload"] if fandom else None)
    active_query = query or person["name"] or ""
    error = f"<p class='mt-4 text-sm text-red-700'>{esc(error_text)}</p>" if error_text else ""
    cards = ""
    if active_query.strip():
        try:
            profiles = wiki_search(active_query)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            profiles = []
            error = f"<p class='mt-4 text-sm text-red-700'>{esc(exc)}</p>"
        if not profiles and not error:
            error = "<p class='mt-4 text-sm text-stone-600'>맞는 위키 문서가 없습니다.</p>"
        cards = "\n".join(wiki_card(person_id, profile, allowed) for profile in profiles)
    hint = "GMMTV Wiki에 없는 항목만 보인다." if gmmtv else "고른 항목만 이 배우의 영어 위키 출처로 저장한다."
    return f"""
    <a href="/people/{person_id}" class="text-sm text-stone-500 hover:text-stone-900">배우</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <h1 class="text-xl font-semibold">영어 위키 검색</h1>
      <p class="mt-2 text-sm text-stone-600">{hint}</p>
      <form method="get" action="/people/{person_id}/wiki" class="mt-4 flex gap-2">
        <input name="q" value="{esc(active_query)}" class="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
        <button class="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white">검색</button>
      </form>
      {error}
    </section>
    <div class="mt-4 space-y-4">{cards}</div>
    """


def wiki_card(person_id: int, profile: dict, allowed: set[str]) -> str:
    checks = []
    for key, label in WIKI_LABELS:
        if key not in allowed or not profile.get(key if key != "image" else "image_url"):
            continue
        if key == "agent":
            label = "소속사 " + ", ".join(
                item["name"] + (f" {item['period_text']}" if item.get("period_text") else "")
                for item in profile["agent"]
            )
            checks.append((key, label))
        elif key == "image" or key in {"career", "fashion", "ambassadorship", "accolades"}:
            checks.append((key, label))
        else:
            checks.append((key, f"{label} {profile[key]}"))
    boxes = "".join(
        f"""<label class="flex items-center gap-2 text-sm">
          <input type="checkbox" name="fields" value="{esc(key)}" checked>
          {esc(label)}
        </label>"""
        for key, label in checks
    )
    return f"""
    <form method="post" action="/people/{person_id}/wiki" class="rounded-lg border border-stone-200 bg-white p-5">
      <input type="hidden" name="title" value="{esc(profile['title'])}">
      <h2 class="text-lg font-semibold">{esc(profile['name'])}</h2>
      <a class="text-sm text-stone-500 underline" href="{esc(profile['url'])}" target="_blank" rel="noreferrer">{esc(profile['title'])}</a>
      {f"<img src='{esc(profile['image_url'])}' alt='' class='mt-3 h-24 w-20 rounded-md object-cover'>" if profile.get("image_url") else ""}
      <div class="mt-3 space-y-2">{boxes or "<p class='text-sm text-stone-600'>가져올 항목이 없습니다.</p>"}</div>
      {prose_block(profile['career'] if 'career' in allowed else '')}
      <button class="mt-4 rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">이 정보 넣기</button>
    </form>
    """


def save_wiki(person_id: int, title: str, fields: list[str]) -> None:
    try:
        profile = fetch_wiki(title)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("영어 위키가 요청을 잠시 막았습니다. 조금 뒤 다시 고르세요") from exc
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
    except urllib.error.URLError as exc:
        raise ValueError("위키 문서를 읽지 못했습니다") from exc
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
            (WIKI_SOURCE, profile["title"], person_id),
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
            (person_id, WIKI_SOURCE, profile["title"], profile["name"], Json(payload)),
        )
        if "agent" in fields and profile.get("agent"):
            save_wiki_spells(conn, person_id, profile["agent"])
        conn.commit()


def sapphic_saved(person: dict, source: dict | None) -> str:
    query = quote(person["name"] or person["mdl_id"])
    link = f"<a class='text-sm font-medium underline' href='/people/{person['id']}/sapphic?q={query}'>검색해서 고르기</a>"
    if source is None:
        return f"""
        <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
          <h2 class="text-sm font-semibold">Sapphic Effect</h2>
          <p class="mt-2 text-sm text-stone-600">선택한 추가 정보가 없습니다.</p>
          <p class="mt-3">{link}</p>
        </section>
        """
    payload = source["payload"] if isinstance(source["payload"], dict) else {}
    company = payload.get("company") or {}
    ships = linked_ships(person["id"])
    socials = payload.get("socials") or []
    ship_html = "".join(
        f"<li><a class='underline' href='{esc('https://www.sapphiceffect.com/ships/' + item['slug'])}' target='_blank' rel='noreferrer'>{esc(item['name'])}</a></li>"
        for item in ships
        if isinstance(item, dict) and item.get("slug") and item.get("name")
    )
    social_html = "".join(
        f"<li><a class='underline' href='{esc(item['url'])}'>{esc(item.get('kind') or item['url'])}</a></li>"
        for item in socials
        if isinstance(item, dict) and item.get("url")
    )
    image = ""
    if payload.get("image_url"):
        image = f"<img src='{esc(payload['image_url'])}' alt='' class='h-24 w-20 rounded-md object-cover'>"
    return f"""
    <section class="mt-6 rounded-lg border border-stone-200 bg-white p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-sm font-semibold">Sapphic Effect</h2>
          <p class="mt-1 text-sm text-stone-600">
            출처 <a class="font-medium text-stone-900 underline" href="{esc(payload.get('url') or '')}" target="_blank" rel="noreferrer">{esc(source['display_name'] or source['external_key'])}</a>
            · {esc(stamp(source['selected_at']))}
          </p>
        </div>
        {link}
      </div>
      <div class="mt-4 flex gap-4">
        {image}
        <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {meta('생일', payload.get('birthday'))}
          {meta('소속사', company.get('name') if isinstance(company, dict) else None)}
        </dl>
      </div>
      {f"<ul class='mt-4 list-disc pl-5 text-sm'>{ship_html}</ul>" if ship_html else ""}
      {f"<ul class='mt-3 list-disc pl-5 text-sm'>{social_html}</ul>" if social_html else ""}
      {prose_block(payload.get("biography"))}
    </section>
    """


def sapphic_search_body(person_id: int, query: str, error_text: str = "") -> str | None:
    with connect() as conn:
        conn.row_factory = dict_row
        person = conn.execute(
            "SELECT id, name, mdl_id FROM person WHERE id = %s",
            (person_id,),
        ).fetchone()
    if person is None:
        return None
    active_query = query or person["name"] or ""
    error = f"<p class='mt-4 text-sm text-red-700'>{esc(error_text)}</p>" if error_text else ""
    cards = ""
    if active_query.strip():
        try:
            profiles = search(active_query)
        except (urllib.error.URLError, TimeoutError) as exc:
            profiles = []
            error = f"<p class='mt-4 text-sm text-red-700'>{esc(exc)}</p>"
        if not profiles and not error:
            error = "<p class='mt-4 text-sm text-stone-600'>맞는 스타 페이지가 없습니다.</p>"
        cards = "\n".join(sapphic_card(person_id, profile) for profile in profiles)
    return f"""
    <a href="/people/{person_id}" class="text-sm text-stone-500 hover:text-stone-900">배우</a>
    <section class="mt-3 rounded-lg border border-stone-200 bg-white p-6">
      <h1 class="text-xl font-semibold">Sapphic Effect 검색</h1>
      <p class="mt-2 text-sm text-stone-600">결과에서 넣을 항목만 고르면 이 배우 상세에 저장된다. MDL 값은 바꾸지 않는다.</p>
      <form method="get" action="/people/{person_id}/sapphic" class="mt-4 flex gap-2">
        <input name="q" value="{esc(active_query)}" class="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
        <button class="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white">검색</button>
      </form>
      {error}
    </section>
    <div class="mt-4 space-y-4">{cards}</div>
    """


def sapphic_card(person_id: int, profile: dict) -> str:
    checks = []
    if profile["birthday"]:
        checks.append(("birthday", f"생일 {profile['birthday']}"))
    if profile["image_url"]:
        checks.append(("image", "프로필 이미지"))
    if profile["company"]:
        checks.append(("company", f"소속사 {profile['company']['name']}"))
    if profile["ships"]:
        checks.append(("ships", f"Ship {len(profile['ships'])}개"))
    if profile["socials"]:
        checks.append(("socials", f"SNS {len(profile['socials'])}개"))
    if profile["biography"]:
        checks.append(("biography", "Biography"))
    boxes = "".join(
        f"""<label class="flex items-center gap-2 text-sm">
          <input type="checkbox" name="fields" value="{esc(key)}" checked>
          {esc(label)}
        </label>"""
        for key, label in checks
    )
    image = ""
    if profile["image_url"]:
        image = f"<img src='{esc(profile['image_url'])}' alt='' class='h-20 w-16 rounded-md object-cover'>"
    return f"""
    <form method="post" action="/people/{person_id}/sapphic" class="rounded-lg border border-stone-200 bg-white p-5">
      <input type="hidden" name="slug" value="{esc(profile['slug'])}">
      <div class="flex gap-4">
        {image}
        <div>
          <h2 class="text-lg font-semibold">{esc(profile['name'])}</h2>
          <a class="text-sm text-stone-500 underline" href="{esc(profile['url'])}">{esc(profile['slug'])}</a>
          <div class="mt-3 space-y-2">{boxes}</div>
          {prose_block(profile["biography"])}
          <button class="mt-4 rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white">이 정보 넣기</button>
        </div>
      </div>
    </form>
    """


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


def tags_block(tags: object) -> str:
    values = [tag for tag in tags if isinstance(tag, str) and tag] if isinstance(tags, (list, tuple)) else []
    chips = "".join(
        f"<span class='rounded-full bg-stone-100 px-2 py-0.5 text-xs'>{esc(tag)}</span>"
        for tag in values
    )
    body = chips or "<span class='text-sm text-stone-500'>없음</span>"
    return f"<div class='mt-4'><p class='text-sm text-stone-500'>태그</p><div class='mt-2 flex flex-wrap gap-2'>{body}</div></div>"


def synopsis_block(text: object) -> str:
    body = prose_block(text)
    if not body:
        return ""
    return f"<h2 class='mt-4 text-sm font-semibold'>설명</h2>{body}"


def prose_block(text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""
    return f"<p class='mt-4 max-h-72 overflow-y-auto whitespace-pre-line text-sm leading-6'>{esc(text)}</p>"


def work_source_line(work: dict) -> str:
    link = work["mdl_url"]
    slug = drama_slug(link)
    collected = ""
    if slug:
        collected = f"· 수집 kuryana <span class='font-mono text-xs'>/v2/dramas/{esc(slug)}</span>"
    original = ""
    if link:
        original = f"<a class='underline' href='{esc(link)}' target='_blank' rel='noreferrer'>원문</a>"
    if not collected and not original:
        return ""
    return f"""
    <p class="mt-3 text-sm text-stone-600">
      출처 <span class="font-medium text-stone-900">MyDramaList</span>
      {collected}
      {original}
    </p>
    """


def source_line(person: dict) -> str:
    mdl_id = person["mdl_id"]
    link = person["mdl_url"]
    original = ""
    if link:
        original = f"<a class='underline' href='{esc(link)}' target='_blank' rel='noreferrer'>원문</a>"
    return f"""
    <p class="mt-3 text-sm text-stone-600">
      출처 <span class="font-medium text-stone-900">MyDramaList</span>
      · 수집 kuryana <span class="font-mono text-xs">/v2/people/{esc(mdl_id)}</span>
      {original}
    </p>
    """


def meta(label: str, value: object) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    return f"<div><dt class='text-stone-500'>{esc(label)}</dt><dd>{esc(text)}</dd></div>"


def status_badge(status: str) -> str:
    css = STATUS_CLASS.get(status, "bg-stone-100 text-stone-700")
    return f"<span class='rounded-full px-2 py-0.5 text-xs font-medium {css}'>{esc(status)}</span>"


def stamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)
