# 화면

storage는 수집과 JSON API다. 화면은 hub다. hub는 DB에 붙지 않고, 수집 규칙을 TypeScript로 다시 쓰지 않는다.

## 실행

Compose 파일은 glow 루트의 `docker-compose.yml`이다. `docker compose up --build -d hub`는 `postgres`, `storage`, `hub`를 같이 띄운다. `app`은 profile `collect`라 이 명령으로 올라가지 않는다.

| 서비스 | 이미지 | 호스트 포트 | 하는 일 |
| --- | --- | --- | --- |
| `postgres` | `postgres:16` | `5433` | DB. 볼륨 `pgdata` |
| `storage` | `storage/Dockerfile` | `8000` | JSON API. 기동 때 스키마 적용 |
| `hub` | `hub/Dockerfile` | `3300` | 화면. 컨테이너 안도 `3300` |
| `app` | `storage/Dockerfile` | 없음 | 수집 CLI. `docker compose run --rm app` |

- 화면: http://127.0.0.1:3300/people
- API: http://127.0.0.1:8000/api/people

hub 컨테이너의 `NUXT_STORAGE_URL`은 `http://host.docker.internal:8000`이다. 서비스 이름 `storage`로 붙지 않는다. `storage`가 꺼지면 화면은 데이터를 못 받는다.

로컬 화면은 `hub`에서 `pnpm install` 후 `pnpm dev`다. 주소는 http://127.0.0.1:3000/people 이고, API는 `http://127.0.0.1:8000`이다.

## 요청 경로

브라우저의 `/api/**`는 `hub/server/middleware/api.ts`가 `NUXT_STORAGE_URL`로 넘긴다. 주소는 이미지 빌드에 굽지 않는다. 서버 렌더는 `runtimeConfig.storageUrl`로 storage에 직접 호출한다.

storage에서 `/api`가 아닌 경로는 404 `{"error":"없는 화면입니다."}`다. HTML은 없다.

## 페이지

| 파일 | URL |
| --- | --- |
| `hub/app/app.vue` | 왼쪽 사이드바 |
| `hub/app/pages/index.vue` | `/` → `/people` |
| `hub/app/pages/people/index.vue` | `/people` |
| `hub/app/pages/people/[id].vue` | `/people/:id` |
| `hub/app/pages/people/[id]/sapphic.vue` | `/people/:id/sapphic` |
| `hub/app/pages/people/[id]/fandom.vue` | `/people/:id/fandom` |
| `hub/app/pages/people/[id]/wiki.vue` | `/people/:id/wiki` |
| `hub/app/pages/works/index.vue` | `/works` |
| `hub/app/pages/works/[id].vue` | `/works/:id` |
| `hub/app/pages/credits/index.vue` | `/credits` |
| `hub/app/pages/credits/[id].vue` | `/credits/:id` |
| `hub/app/pages/companies/index.vue` | `/companies` |
| `hub/app/pages/companies/[id].vue` | `/companies/:id` |

사이드바 대메뉴는 수집이다. 하위는 배우, 작품, 작가·감독, 종합 콘텐츠 스튜디오다. 배우 등록은 배우 목록의 버튼이 모달을 연다.

## API

접두사는 `/api`다. 실패 본문은 `{"error":"<메시지>"}`다. `datetime`은 ISO 8601 문자열, `rating`은 숫자 또는 `null`이다.

| 메서드 | 경로 | 성공 |
| --- | --- | --- |
| GET | `/api/people` | 200 `{"people":[...]}`. 행에 `works`, `hidden` 정수 |
| POST | `/api/people` | 200 `{"person_id","mdl_id","status","works"}` |
| GET | `/api/people/{id}` | 200 상세. 없으면 404 `없는 배우입니다.` |
| POST | `/api/people/{id}/delete` | 200 `{"ok":true}`. 역할 `a`가 아니면 404 |
| POST | `/api/people/works` | 202 `{"on":true}` |
| GET | `/api/people/works/progress` | 200 `{on,done,total,name,rows}` |
| GET | `/api/works?deleted=` | 200 `{"deleted","works":[...]}`. `deleted`는 `0` `1` `all`. 그 밖은 `0` |
| GET | `/api/works/{id}` | 200. 없거나 `deleted = 1`이면 404 `없는 작품입니다.` |
| POST | `/api/works/{id}/exception` | 200 `{"ok":true,"deleted"}` |
| POST | `/api/works/{id}/episodes` | 200 `{"ok":true}` |
| POST | `/api/works/{id}/credits` | 200 `{"ok":true}` |
| POST | `/api/works/{id}/tmdb` | 200 `{"ok":true}` |
| GET | `/api/credits` | 200 `{"credits":[...]}` |
| GET | `/api/credits/{id}` | 200. 없으면 404 `없는 작가·감독입니다.` |
| GET | `/api/companies` | 200 `{"companies":[...]}` |
| GET | `/api/companies/{id}` | 200. 없으면 404 `없는 종합 콘텐츠 스튜디오입니다.` |
| POST | `/api/companies/{id}` | 200 `{"ok":true}` |
| GET | `/api/people/{id}/sapphic?q=` | 200. 배우 없으면 404 |
| POST | `/api/people/{id}/sapphic` | 200 `{"ok":true}` |
| GET | `/api/people/{id}/fandom?q=` | 200. GMMTV가 아니면 `blocked: true` |
| POST | `/api/people/{id}/fandom` | 200 `{"ok":true}` |
| GET | `/api/people/{id}/wiki?q=` | 200 |
| POST | `/api/people/{id}/wiki` | 200 `{"ok":true}` |

POST 본문은 JSON 객체다. `Content-Type`이 JSON이 아니거나 객체가 아니면 400 `{"error":"JSON 객체가 아닙니다"}`. `ValueError`는 400이다.

```json
{ "mdl_id": "70935" }
{ "tmdb_id": "123", "tmdb_kind": "tv" }
{ "logo_url": "https://...", "homepage": "https://..." }
{ "slug": "freen", "fields": ["birthday", "company"] }
{ "title": "Freen Sarocha", "fields": ["birthday"] }
{ "title": "Freen Sarocha", "lang": "en", "fields": ["career"] }
```

`fields`가 없으면 `[]`다. `lang`이 없으면 `en`이다.

`/api/people/works`와 `/api/people/works/progress`는 `/api/people/{id}`보다 먼저 매칭한다.

## 화면 동작

- 출연 수는 API의 `works`, `hidden`을 화면에서 `40(7)`로 붙인다.
- GL/BL: `Lesbian Romance` → GL, `Gay Romance` 또는 `Gay Male Lead` → BL. 같은 표기는 한 번만.
- 삭제 확인 문구는 `이 배우와 연결을 삭제합니다. 작품과 소속사는 남습니다.`
- 작품 상세 GET은 storage 안에서 `save_drama_detail`을 한 번 호출한다. hub가 episodes, credits를 자동으로 치지 않는다.
- 작품 필터 `deleted=1`인 제목은 링크가 아니다. 예외 처리 뒤 목록은 `/works?deleted=0`이다.
- 영화 상세에는 에피소드 칸이 없다.
- GMMTV가 아니면 GMMTV Wiki 검색 칸을 그리지 않는다. 차단 문구는 `Sapphic Effect 소속사가 GMMTV일 때만 GMMTV Wiki를 찾는다.`
- 작품 가져오기는 2초마다 진행을 읽고, 진행 중이면 해당 행만 갱신한다.
- `serve()`는 스키마 적용, `backfill_sapphic`, `move_credits`, `move_ships` 후 `fill_drama_details` 스레드를 남긴다.
