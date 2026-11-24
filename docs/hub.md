# hub 화면 분리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `storage`는 수집과 JSON만 하고, 지금 `storage/app/web.py`가 그리는 화면은 `hub`의 Nuxt로 그대로 옮긴다.

**Architecture:** 브라우저가 보는 서버는 hub다. hub는 `/api/**`를 storage `http://127.0.0.1:8000`으로 프록시한다. storage는 PostgreSQL과 기존 Python 수집 함수를 호출해 JSON을 돌려준다. hub는 DB에 붙지 않고, 수집 규칙을 TypeScript로 다시 쓰지 않는다. 화면 경로와 한국어 라벨은 현재와 같다.

**Tech Stack:** storage는 지금 스택(Python 3.12, `http.server`, psycopg, PostgreSQL 16, Docker Compose). hub는 `npm create nuxt@latest -- --template ui`가 만드는 Nuxt + `@nuxt/ui` + Tailwind CSS.

## Global Constraints

- 스키마, upsert, 외부 API 규칙은 [docs/design.md](design.md), [docs/plan.md](plan.md), [docs/apis.md](apis.md) 그대로다. 이 작업은 화면 위치만 바꾼다.
- hub는 `DATABASE_URL`을 쓰지 않는다. SQL은 `storage/app`에만 있다.
- 화면 추가, 인증, 리디자인, hub Docker 이미지, kuryana 자체 호스팅은 하지 않는다.
- 브라우저 주소는 hub `http://127.0.0.1:3000`이다. storage `8000`은 API다.
- JSON 객체 키는 이 문서의 응답 예와 같다. `datetime`은 ISO 8601 문자열, `rating`은 숫자 또는 `null`, 없는 텍스트는 `null`, 없는 목록은 `[]`다.
- 실패 본문은 `{"error": "<메시지>"}`다. 메시지는 지금 `web.py`의 `ValueError` 문장과 404 문장을 그대로 쓴다.
- 작품 상세 GET은 지금처럼 `save_drama_detail(work_id)`를 호출한다. `detail_at`이 비어 있으면 그 요청 안에서 드라마 상세를 채운다. hub는 같은 목적으로 수집 API를 한 번 더 치지 않는다.
- `serve()`의 스키마 적용, `backfill_sapphic`, `move_credits`, `move_ships`, `fill_drama_details` 백그라운드 스레드는 남긴다.
- 삭제 확인 문구는 `이 배우와 연결을 삭제합니다. 작품과 소속사는 남습니다.`
- 출연 수는 보이는 수와 숨긴 수를 `40(7)`로 보여 준다. API는 `works`, `hidden` 정수 둘이다. 이어 붙이는 곳은 hub다.
- GL/BL 표시 규칙은 지금과 같다. `Lesbian Romance` → GL, `Gay Romance` → BL, `Gay Male Lead` → BL. 같은 표기는 한 번만.
- 커밋은 사용자가 요청할 때만 한다. 아래 커밋 단계는 요청이 있을 때의 메시지다.

---

## 파일

| 경로 | 책임 |
| --- | --- |
| `storage/app/api.py` | 조회 SQL과 JSON 응답. 수집 함수 호출. HTML 없음 |
| `storage/app/web.py` | `/api/*`를 `api.py`로 넘긴 뒤, 마지막 태스크에서 HTML 생성 삭제 |
| `storage/templates/` | 마지막 태스크에서 삭제 |
| `storage/Dockerfile` | `COPY templates` 삭제 |
| `hub/` | Nuxt 앱. 페이지는 아래 경로표 |
| `README.md` | hub 실행 방법. storage 웹 주소 설명을 API로 수정 |
| `docs/design.md` | 맨 위에 hub 포인터 한 줄 |

hub 페이지. 템플릿이 `app/pages`를 만들면 그 아래, `pages`만 만들면 `pages` 아래다. 아래 경로는 `app/pages` 기준이다.

| 파일 | URL |
| --- | --- |
| `app/app.vue` | 공통 헤더 |
| `app/pages/index.vue` | `/` → `/people` |
| `app/pages/people/index.vue` | `/people` |
| `app/pages/register.vue` | `/register` |
| `app/pages/people/[id].vue` | `/people/:id` |
| `app/pages/people/[id]/sapphic.vue` | `/people/:id/sapphic` |
| `app/pages/people/[id]/fandom.vue` | `/people/:id/fandom` |
| `app/pages/people/[id]/wiki.vue` | `/people/:id/wiki` |
| `app/pages/works/index.vue` | `/works` |
| `app/pages/works/[id].vue` | `/works/:id` |
| `app/pages/credits/index.vue` | `/credits` |
| `app/pages/credits/[id].vue` | `/credits/:id` |
| `app/pages/companies/index.vue` | `/companies` |
| `app/pages/companies/[id].vue` | `/companies/:id` |

## API

기존 HTML 라우트와 1:1이다. 접두사는 `/api`다.

| 메서드 | 경로 | 지금 함수 | 성공 |
| --- | --- | --- | --- |
| GET | `/api/people` | `_listed_people` | 200 `{"people":[...]}` |
| POST | `/api/people` | `register` | 200 `{"person_id","mdl_id","status","works"}` |
| GET | `/api/people/{id}` | `person_body`의 조회 | 200 상세. 없으면 404 `없는 배우입니다.` |
| POST | `/api/people/{id}/delete` | `delete_person` | 200 `{"ok":true}`. `a` 아니면 404 `없는 배우입니다.` |
| POST | `/api/people/works` | `start_work_refresh` | 202 `{"on":true}` |
| GET | `/api/people/works/progress` | `work_progress_payload` | 200. HTML 문자열을 넣지 않는다 |
| GET | `/api/works?deleted=` | `works_body` | 200 `{"deleted","works":[...]}`. `deleted`는 `0` `1` `all`. 그 밖은 `0` |
| GET | `/api/works/{id}` | `work_body` | 200. 없거나 `deleted = 1`이면 404 `없는 작품입니다.` |
| POST | `/api/works/{id}/exception` | `hide_work` | 200 `{"ok":true,"deleted":"<그대로 돌려준 필터>"}` |
| POST | `/api/works/{id}/episodes` | `collect_episodes` | 200 `{"ok":true}`. `ValueError`는 400 |
| POST | `/api/works/{id}/credits` | `collect_credits` | 200 `{"ok":true}`. `ValueError`는 400 |
| POST | `/api/works/{id}/tmdb` | `save_tmdb` | 200 `{"ok":true}`. `ValueError`는 400 |
| GET | `/api/credits` | `credits_body` | 200 `{"credits":[...]}` |
| GET | `/api/credits/{id}` | `credit_body` | 200. 없으면 404 `없는 작가·감독입니다.` |
| GET | `/api/companies` | `companies_body` | 200 `{"companies":[...]}` |
| GET | `/api/companies/{id}` | `company_body` | 200. 없으면 404 `없는 종합 콘텐츠 스튜디오입니다.` |
| POST | `/api/companies/{id}` | `save_company_urls` | 200 `{"ok":true}`. `ValueError`는 400 |
| GET | `/api/people/{id}/sapphic?q=` | `sapphic_search_body` | 200. 배우 없으면 404 |
| POST | `/api/people/{id}/sapphic` | `save_sapphic` | 200 `{"ok":true}` |
| GET | `/api/people/{id}/fandom?q=` | `fandom_search_body` | 200. GMMTV가 아니면 `blocked: true` |
| POST | `/api/people/{id}/fandom` | `save_fandom` | 200 `{"ok":true}` |
| GET | `/api/people/{id}/wiki?q=` | `wiki_search_body` | 200 |
| POST | `/api/people/{id}/wiki` | `save_wiki` | 200 `{"ok":true}` |

POST 본문은 JSON이다.

```json
{ "mdl_id": "70935" }
{ "tmdb_id": "123", "tmdb_kind": "tv" }
{ "logo_url": "https://...", "homepage": "https://..." }
{ "slug": "freen", "fields": ["birthday", "company"] }
{ "title": "Freen Sarocha", "fields": ["birthday"] }
{ "title": "Freen Sarocha", "lang": "en", "fields": ["career"] }
```

`fields`가 없으면 `[]`다. `lang`이 없으면 `en`이다.

진행 응답. `rows`는 배우 목록과 같은 행이다.

```json
{ "on": true, "done": 1, "total": 4, "name": "Freen", "rows": [] }
```

검색 응답.

```json
{
  "person": { "id": 1, "name": "", "stage_name": "", "mdl_id": "" },
  "query": "",
  "blocked": false,
  "message": "",
  "hint": "",
  "allowed": [],
  "profiles": []
}
```

`profiles`는 `app.sapphic.search`, `app.fandom.search`, `app.wikipedia.search`가 이미 돌려주는 dict다. hub용으로 키를 새로 만들지 않는다. fandom은 `blocked`일 때 `profiles`를 비운다. wiki의 `allowed`는 `gaps()` 결과다. sapphic·fandom은 `allowed`를 `[]`로 둔다.

---

### Task 1: JSON 응답 껍데기

**Files:**
- Create: `storage/app/api.py`
- Modify: `storage/app/web.py` (`Handler.do_GET`, `Handler.do_POST`)

**Interfaces:**
- Consumes: 없음
- Produces: `dispatch(method: str, path: str, query: dict[str, list[str]], body: dict | None) -> tuple[int, dict]`. `ApiError(status: int, message: str)`.

- [ ] **Step 1: `api.py`에 직렬화와 404 디스패치**

```python
import json
from datetime import datetime
from decimal import Decimal

class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


def encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value))


def dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=encode).encode()


def dispatch(method: str, path: str, query: dict, body: dict | None) -> tuple[int, dict]:
    raise ApiError(404, "없는 화면입니다.")
```

- [ ] **Step 2: `web.py`가 `/api/`만 JSON으로 응답**

`do_GET` 맨 앞, `do_POST`에서 본문을 읽은 뒤. HTML 분기는 그대로 둔다. `web.py`는 `from app.api import ApiError, dispatch, dumps`만 가져온다. `api.py`는 `web`을 import하지 않는다.

```python
def respond_json(self, status: int, payload: dict) -> None:
    raw = dumps(payload)
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(raw)))
    self.end_headers()
    self.wfile.write(raw)


def api(self, method: str, query: dict, body: dict | None) -> None:
    path = urlparse(self.path).path
    try:
        status, payload = dispatch(method, path, query, body)
    except ApiError as exc:
        status, payload = exc.status, {"error": exc.message}
    self.respond_json(status, payload)
```

GET `/api/...`는 `self.api("GET", parse_qs(...), None)` 후 return. POST `/api/...`는 JSON 객체를 읽어 `self.api("POST", {}, body)` 후 return. `Content-Type`이 JSON이 아니거나 객체가 아니면 400 `{"error":"JSON 객체가 아닙니다"}`.

- [ ] **Step 3: 확인**

glow 루트에서 `docker compose up --build web` 뒤.

```bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/people
curl -s http://127.0.0.1:8000/people | head -c 40
```

Expected: 첫 줄 `404`. 둘째는 `<!DOCTYPE html>`로 시작하는 HTML. 기존 화면은 이 태스크에서 깨지지 않는다.

- [ ] **Step 4: Commit**

```bash
git add storage/app/api.py storage/app/web.py
git commit -m "feat: add JSON dispatch shell on storage"
```

### Task 2: 목록·상세 조회

**Files:**
- Modify: `storage/app/api.py`
- Modify: `storage/app/web.py` (조회 SQL을 함수로 빼서 HTML과 API가 같이 씀)

**Interfaces:**
- Consumes: `dispatch`
- Produces: 위 표의 GET 전부. POST는 아직 404.

HTML 조립 함수는 이 태스크에서 지우지 않는다. SQL만 `_listed_people`처럼 dict를 돌려주는 함수로 모으고, 기존 `*_body`는 그 dict로 지금 HTML을 만든다.

- [ ] **Step 1: 배우 목록**

`GET /api/people`는 `_listed_people()` 행을 아래 키로 돌려준다.

`id`, `mdl_id`, `name`, `native_name`, `nationality`, `image_url`, `collect_status`, `collected_at`, `works`, `hidden`.

`works`와 `hidden`은 int.

- [ ] **Step 2: 나머지 GET**

각 응답 키:

- 배우 상세 `person`: `person` 행 전체. `works[]`: `id`, `title`, `kind`, `year`, `episodes`, `rating`, `mdl_id`, `role`, `character_name`. `affiliations[]`: `company_id`, `name`, `start_year`, `end_year`, `period_text`, `is_current`. `ships[]`: `slug`, `name`, `image_url`. `actor`: bool. `sources`: 키 `sapphic_effect`, `gmmtv_fandom`, `en_wikipedia`. 값은 `person_source` 행 또는 `null`.
- 작품 목록 항목: `id`, `title`, `kind`, `year`, `episodes`, `rating`, `image_url`, `tags`, `deleted`, `cast_count`.
- 작품 상세: `work` 행, `cast[]` (`id`, `name`, `native_name`, `role`, `character_name`), `episodes[]` (영화면 `[]`이고 키 `episodes`는 있어도 hub가 칸을 그리지 않음), `credits[]` (`id`, `name`, `native_name`, `image_url`, `role`), `providers[]` (`country`, `name`, `offer`, `url`), `networks[]` (`id`, `name`). 호출 전에 `save_drama_detail`.
- 작가 목록 항목: `id`, `name`, `native_name`, `nationality`, `image_url`, `roles`, `works`.
- 작가 상세: `person` 행, `works[]` (`id`, `title`, `kind`, `year`, `role`).
- 회사 목록 항목: `id`, `name`, `logo_url`, `members`, `types`.
- 회사 상세: `company` 행, `types[]` 이름 문자열, `works[]` (`id`, `title`, `year`), `people[]` (`id`, `name`, `native_name`, `period_text`, `is_current`, `start_year`).
- 검색 GET: 위 검색 응답. 외부 호출 `URLError`/`TimeoutError`/`ValueError`는 200에 `message`로 넣지 않는다. 502 `{"error":"<예외 문자열>"}`.

- [ ] **Step 3: 확인**

```bash
curl -s http://127.0.0.1:8000/api/people
curl -s 'http://127.0.0.1:8000/api/works?deleted=0'
curl -s http://127.0.0.1:8000/api/credits
curl -s http://127.0.0.1:8000/api/companies
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/people
```

Expected: 네 JSON은 객체. 마지막은 `200`.

- [ ] **Step 4: Commit**

```bash
git add storage/app/api.py storage/app/web.py
git commit -m "feat: expose read JSON for current screens"
```

### Task 3: 수집·수정 POST

**Files:**
- Modify: `storage/app/api.py`

**Interfaces:**
- Consumes: `register`, `delete_person`, `start_work_refresh`, `hide_work`, `collect_episodes`, `collect_credits`, `save_tmdb`, `save_company_urls`, `save_sapphic`, `save_fandom`, `save_wiki`
- Produces: 위 표의 POST. `ValueError`는 400 `{"error": str(exc)}`.

- [ ] **Step 1: 등록과 새로고침**

`POST /api/people`는 `register(mdl_id)` 결과를 `person_id`, `mdl_id`, `status`, `works`로 돌려준다. `POST /api/people/works`는 `start_work_refresh()` 후 202. 이미 돌고 있거나 대상이 없어도 202이고, 진행 GET의 `on`으로 구분한다.

- [ ] **Step 2: 작품·회사·출처 저장**

경로표의 POST를 연결한다. 삭제·예외·에피소드·작가·TMDB·회사 URL·sapphic·fandom·wiki. 입력 검증은 기존 함수에 맡긴다. API는 잡고 상태 코드만 바꾼다.

`delete_person`, `hide_work`, `start_work_refresh`, 진행용 전역, `save_sapphic`, `save_fandom`, `save_wiki`, `save_company_urls`는 이 태스크에서 `api.py`로 옮긴다. `web.py`의 HTML은 그 함수를 import해서 그대로 쓴다. 반대 방향 import는 없다.

- [ ] **Step 3: 확인**

없는 id로 지운다. 로고 검사는 회사 존재 검사보다 먼저다.

```bash
curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/people/999999999/delete
curl -s -X POST http://127.0.0.1:8000/api/companies/999999999 \
  -H 'Content-Type: application/json' \
  -d '{"logo_url":"nope","homepage":""}'
```

Expected: `404`, 그다음 `400`과 `로고 주소가 아닙니다`. 존재하는 배우 id로 등록·삭제 확인은 하지 않는다. 행이 지워진다.

- [ ] **Step 4: Commit**

```bash
git add storage/app/api.py
git commit -m "feat: expose collect actions as JSON"
```

### Task 4: hub 스캐폴드

**Files:**
- Create: `hub/` (템플릿 산출물)
- Modify: `hub/nuxt.config.ts`, `hub/app/app.vue` 또는 템플릿이 만든 동일 파일, `hub/app/assets/css/main.css`

**Interfaces:**
- Consumes: storage `http://127.0.0.1:8000/api/**`
- Produces: `http://127.0.0.1:3000/api/**` 프록시. `UApp`으로 감싼 레이아웃.

- [ ] **Step 1: 템플릿**

저장소 루트에서. 이미 git 저장소이므로 hub 안에 git을 만들지 않는다.

```bash
npm create nuxt@latest hub -- --template ui --packageManager npm --gitInit false
```

CLI가 물으면 npm, git init 안 함. `@nuxt/ui`와 Tailwind는 이 템플릿이 넣는다. Tailwind를 따로 설치하거나 `tailwind.config`를 추가하지 않는다.

- [ ] **Step 2: 프록시와 레이아웃**

`nuxt.config.ts`의 `modules`에 `@nuxt/ui`가 있는지 확인하고, 없으면 넣는다. CSS import가 템플릿에 있으면 유지한다.

```ts
const storage = process.env.NUXT_STORAGE_URL || 'http://127.0.0.1:8000'

export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  routeRules: {
    '/api/**': { proxy: `${storage}/api/**` }
  }
})
```

`app.vue`는 `UApp` 안에 헤더와 `NuxtPage`다. 링크는 지금 `templates/layout.html`과 같다.

- Glow → `/people`
- 배우 등록 → `/register`
- 배우 → `/people`
- 작품 → `/works`
- 작가·감독 → `/credits`
- 종합 콘텐츠 스튜디오 → `/companies`

너비는 `max-w-5xl`. 헤더는 `UHeader` 또는 `header` + `UButton`/`NuxtLink`. 새 메뉴는 없다.

`app.config.ts`가 생기면 primary를 `neutral`로 둔다. 색을 새로 정의하지 않는다.

```ts
export default defineAppConfig({
  ui: { colors: { primary: 'neutral' } }
})
```

- [ ] **Step 3: 확인**

storage가 떠 있는 상태에서 `hub`에서 `npm run dev`.

```bash
curl -s http://127.0.0.1:3000/api/people
```

Expected: Task 2와 같은 JSON. hub HTML에 `Glow` 링크가 있다.

- [ ] **Step 4: Commit**

```bash
git add hub
git commit -m "feat: scaffold hub with Nuxt UI"
```

`hub/node_modules`는 템플릿 `.gitignore`에 맡긴다. 올라가면 빼고 다시 커밋하지 말고, 그 커밋을 만들지 않는다.

### Task 5: 목록 네 화면

**Files:**
- Create: `hub/app/pages/index.vue`
- Create: `hub/app/pages/people/index.vue`
- Create: `hub/app/pages/works/index.vue`
- Create: `hub/app/pages/credits/index.vue`
- Create: `hub/app/pages/companies/index.vue`

**Interfaces:**
- Consumes: `GET /api/people`, `GET /api/people/works/progress`, `POST /api/people/works`, `GET /api/works`, `POST /api/works/{id}/exception`, `GET /api/credits`, `GET /api/companies`
- Produces: 네 목록과 `/` 리다이렉트

- [ ] **Step 1: `/`와 배우 목록**

`index.vue`는 `navigateTo('/people', { redirectCode: 302 })`.

`people/index.vue`는 `useFetch('/api/people')`. 열은 썸네일, 이름(`native_name`이 있고 표시 이름과 다르면 아래 작은 글자), MDL id, 국적, 상태, 출연, 수집 시각. 이름 링크는 `/people/{id}`. 상태 색은 `collected` 초록, `failed` 빨강, `registered` 주황. `UBadge`. 시각은 `YYYY-MM-DD HH:MM`. 빈 목록 문구는 `등록된 배우가 없습니다.` 제목 옆 숫자는 행 수.

`작품 가져오기`는 `POST /api/people/works` 후 진행을 2초마다 `GET /api/people/works/progress`로 읽는다. `on`이면 `작품 {done}/{total} · {name}`과 막대(`done * 100 / total`, total 0이면 0). `rows`로 그 행의 출연·상태·시각만 바꾼다. 목록 전체를 다시 그리지 않는다. `on`이 아니면 폴링을 멈춘다.

- [ ] **Step 2: 작품·작가·회사 목록**

작품 필터는 `USelect` 값 `all`/`0`/`1`, 라벨 `All`/`Show`/`Hide`. 쿼리 `deleted`. 기본 `0`. 열은 썸네일, 제목, 종류(드라마/영화/TV 쇼), 연도, 에피소드, 평점, 출연, 예외. `deleted = 1`인 제목은 링크가 아니다. 그 외 제목은 `/works/{id}`. 예외는 `POST /api/works/{id}/exception` 후 같은 `deleted` 필터로 남는다. 빈 문구 `수집된 작품이 없습니다.`

작가 열: 썸네일, 이름, 역할, 국적, 작품. 링크 `/credits/{id}`. 역할 문자는 API `roles`를 받아 hub에서 만든다. `Screenwriter` 또는 `Screenwriter & Director`가 있고 `Director` 또는 `Screenwriter & Director`가 있으면 `작가·감독`. 아니면 `Screenwriter & Director` → `작가·감독`, `Director` → `감독`, `Screenwriter` → `작가`. 빈 문구 `수집된 작가·감독이 없습니다.`

회사 열: 로고 50px, 이름, 타입, 소속 배우. 링크 `/companies/{id}`. 빈 문구 `등록된 종합 콘텐츠 스튜디오가 없습니다.`

- [ ] **Step 3: 확인**

브라우저에서 `http://127.0.0.1:3000/people`, `/works`, `/credits`, `/companies`. 각 목록이 storage HTML과 같은 행을 보여 주는지, 작품 필터 세 값, 배우가 0명이면 빈 문구. `작품 가져오기`는 배우가 있을 때만 누르고, 진행 숫자가 2초마다 바뀌다 끝나는지 본다. 끝나면 출연·상태·시각이 갱신된다.

- [ ] **Step 4: Commit**

```bash
git add hub/app/pages
git commit -m "feat: add hub list pages"
```

### Task 6: 상세 네 화면

**Files:**
- Create: `hub/app/pages/register.vue`
- Create: `hub/app/pages/people/[id].vue`
- Create: `hub/app/pages/works/[id].vue`
- Create: `hub/app/pages/credits/[id].vue`
- Create: `hub/app/pages/companies/[id].vue`

**Interfaces:**
- Consumes: Task 2·3의 상세 GET과 등록·삭제·예외·에피소드·작가·TMDB·회사 POST
- Produces: 등록 후 `/people/{person_id}`로 이동

- [ ] **Step 1: 등록과 배우 상세**

등록 입력 하나. 라벨은 MDL 숫자 id. `POST /api/people`. 성공하면 `/people/{person_id}`. 400이면 `error`를 폼 위에 보여 준다.

배우 상세는 지금 `person_body`의 칸만 그린다. 활동명, MDL id, 국적, 성별, 생일, 다른 이름, 출처 줄(MyDramaList, `/v2/people/{mdl_id}`, `mdl_url` 원문), `collect_error`, 소속, Sapphic Effect, GMMTV Wiki, 위키, 출연작. `actor`일 때만 삭제. 삭제는 `confirm` 후 `POST /api/people/{id}/delete`, 성공하면 `/people`. 출연작 열: 제목, 종류, 연도, 구분, 배역, 평점. 제목은 `/works/{id}`. 소속 회사는 `/companies/{company_id}`. 출처에 고르기 링크가 있으면 각각 sapphic, fandom, wiki 경로에 `q`로 활동명 또는 이름을 붙인다. 지금 `web.py`의 링크 조건(GMMTV일 때만 fandom 링크)을 유지한다.

- [ ] **Step 2: 작품·작가·회사 상세**

작품. 404면 `없는 작품입니다.` 제목, 예외 버튼, 원제, 종류, 연도, 회차, 평점, MDL id, 방영, 방영일, 등급, 홈페이지, 방송사, TMDB 폼, 태그, 출처 줄, 설명, 작가·감독, 에피소드, 출연. `kind === 'movie'`면 에피소드 칸을 그리지 않는다. 예외 성공 후 `/works?deleted=0`. 에피소드·작가 가져오기와 TMDB 다시 가져오기는 해당 POST 후 같은 상세를 다시 읽는다. 400이면 상세 안에 `error`. TMDB 제공처는 `KR` 한국, `TH` 태국. `flatrate` 등 한글 라벨은 API `offer`를 그대로 보여 준다. 홈페이지와 제공처 `url`은 `http://` 또는 `https://`일 때만 새 창 링크.

작가 상세. 404면 `없는 작가·감독입니다.` 프로필 칸, `about`, `socials`의 `http` URL, 작품 표. 작품 역할은 감독/작가/작가·감독.

회사 상세. 로고 150px, 타입, 홈페이지, 로고 URL, 홈페이지 URL, 저장, 작품, 소속 배우. 저장은 POST 후 다시 읽기. 400이면 폼 아래 `error`.

- [ ] **Step 3: 확인**

`/register`에 `70935`가 이미 있으면 그 상세로 가는지만 본다. 새 수집을 일부러 돌리지 않아도 된다. 없는 `/people/999999999`는 404 문구. 영화 상세에 에피소드 버튼이 없다. 드라마 상세에는 있다. 회사 저장에 `notaurl`을 넣으면 `로고 주소가 아닙니다` 또는 `홈페이지 주소가 아닙니다`.

- [ ] **Step 4: Commit**

```bash
git add hub/app/pages
git commit -m "feat: add hub detail pages"
```

### Task 7: 출처 고르기 세 화면

**Files:**
- Create: `hub/app/pages/people/[id]/sapphic.vue`
- Create: `hub/app/pages/people/[id]/fandom.vue`
- Create: `hub/app/pages/people/[id]/wiki.vue`

**Interfaces:**
- Consumes: 검색 GET/POST
- Produces: 저장 성공 시 `/people/{id}`

- [ ] **Step 1: 세 페이지**

공통: 뒤로 `배우` → `/people/{id}`. 검색창은 `q`. 처음 값은 API `query`. 결과 카드마다 체크박스 `fields`. 기본은 체크. 버튼 `이 정보 넣기`. 저장 POST 성공 시 배우 상세로. 400/502는 `error`.

Sapphic 설명: `결과에서 넣을 항목만 고르면 이 배우 상세에 저장된다. MDL 값은 바꾸지 않는다.` 카드 키는 프로필에 있는 것만. `birthday`, `image`, `company`, `ships`, `socials`, `biography`. hidden `slug`.

Fandom. `blocked`면 검색창 없이 `message`만. 설명: `고른 항목만 이 배우의 GMMTV Wiki 출처로 저장한다.` hidden `title`. 항목은 프로필에 값이 있는 `birth_name`, `nickname`, `native_name`, `birthday`, `birth_place`, `height`, `weight`, `years_active`, `image`, `socials`, `early_life`.

Wiki 설명은 API `hint`. hidden `title`, `lang`. 체크박스는 `allowed`에 있고 값이 있는 항목만. 키는 `image`, `birth_name`, `native_name`, `birthday`, `birth_place`, `height`, `education`, `years_active`, `agent`, `career`, `fashion`, `ambassadorship`, `accolades`. `agent` 라벨은 `소속사` 뒤에 이름과 `period_text`.

- [ ] **Step 2: 확인**

배우 상세의 고르기 링크로 들어가 검색어가 채워져 있는지. GMMTV가 아닌 배우의 fandom URL은 검색창이 없다. 저장은 기존에 연결된 문서를 다른 배우에 넣지 않는다. 그 경우 400 `이미 다른 배우에 연결된`으로 시작하는 문장.

- [ ] **Step 3: Commit**

```bash
git add hub/app/pages/people
git commit -m "feat: add hub source picker pages"
```

### Task 8: storage HTML 제거

**Files:**
- Modify: `storage/app/web.py`
- Delete: `storage/templates/layout.html`, `storage/templates/register.html`
- Modify: `storage/Dockerfile`
- Modify: `README.md`
- Modify: `docs/design.md`

**Interfaces:**
- Consumes: Task 1–7
- Produces: storage는 `/api/*`와 `serve`만. `/people` HTML은 404 JSON.

- [ ] **Step 1: HTML 삭제**

`web.py`에서 템플릿 읽기, `page`, `*_body`, HTML 조각 함수를 지운다. `do_GET`/`do_POST`의 HTML 분기를 지운다. `/api`가 아닌 경로는 404 `{"error":"없는 화면입니다."}`. Task 3에서 `api.py`로 옮긴 함수의 복사본이 `web.py`에 남아 있으면 지운다.

`Dockerfile`의 `COPY templates ./templates`를 지운다.

- [ ] **Step 2: 문서**

`docs/design.md` 첫 단락 끝에 한 줄.

`화면은 [docs/hub.md](hub.md)의 hub가 그린다. storage serve는 JSON API다.`

`README.md`에 `화면` 절을 추가한다. 명령은 `cd hub`, `npm install`, `npm run dev`. 화면 주소는 `http://127.0.0.1:3000/people`, API 주소는 `http://127.0.0.1:8000/api/people`. storage `web`이 8000에 떠 있어야 한다고 적는다. storage 절의 `웹: http://localhost:8000`은 `API: http://localhost:8000/api/people`로 바꾼다.

- [ ] **Step 3: 확인**

```bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/people
curl -s http://127.0.0.1:3000/api/people
```

Expected: `404`. hub 목록·상세·등록 폼·작품 필터·회사 저장 실패 문구가 Task 5–7과 같다. CLI는 그대로다.

```bash
docker compose run --rm app register 70935
```

Expected: `collected` 또는 기존과 같은 `failed`. 화면 코드 없이 수집된다.

- [ ] **Step 4: Commit**

```bash
git add storage/app/web.py storage/app/api.py storage/Dockerfile storage/templates README.md docs/design.md
git commit -m "feat: move screens from storage to hub"
```

## 끝난 뒤 볼 것

- storage 컨테이너에 템플릿 경로가 없어 기동이 깨지지 않는지. `COPY templates`가 남은 채 디렉터리를 지우면 빌드가 실패한다.
- 작품 상세를 열 때 상세 수집이 두 번 돌지 않는지. 네트워크에서 `GET /api/works/{id}`가 한 번이고, hub가 `/episodes`나 `/credits`를 자동으로 치지 않아야 한다.
- 진행 폴링이 목록 전체를 교체하지 않는지.

하지 않은 것: 인증, 새 정보 구조, 다크 모드 설정, hub를 Compose 서비스로 넣기, storage CORS, TypeScript로 수집 재구현.
