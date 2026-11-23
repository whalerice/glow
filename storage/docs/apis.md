# 외부 소스

이 문서가 적는 것은 앱이 실제로 호출하는 주소와, 그 응답에서 저장하는 필드다. 공식 문서 전체를 옮기지 않는다.

공통 `User-Agent`는 `glow-collect/0.1`이다. 위키 둘은 `HTTP_USER_AGENT`가 있으면 그 값을 쓴다.

## 1. kuryana

MyDramaList JSON. 기본 호스트는 `https://kuryana.tbdh.app`. `KURYANA_BASE_URL`로 바꾼다. 끝 슬래시는 제거한다.

출처: [tbdsux/kuryana](https://github.com/tbdsux/kuryana). Swagger는 `{KURYANA_BASE_URL}/docs`.

성공 응답은 `success: true`와 `data`다. 인물 조회는 바깥 `link`도 쓴다. `success`가 true가 아니거나 HTTP가 200이 아니면 그 호출은 실패다.

작품 slug는 `780112-girl-rules`처럼 숫자와 영문 제목이 붙는다. 경로에 넣을 때 URL 인코딩한다.

### `GET /v2/people/{id}`

배우 등록과 작가·감독 프로필. `{id}`는 MDL 숫자만.

| 응답 | 저장 |
| --- | --- |
| `link` | `person.mdl_url` |
| `data.name` | `person.name`. 활동명 분리에도 쓴다 |
| `data.native_name` | `person.native_name` |
| `data.first_name`, `data.family_name` | `person.first_name`, `person.family_name`, `person.stage_name` |
| `data.also_known_as` | `person.also_known_as`. 없으면 `[]` |
| `data.nationality` | `person.nationality` |
| `data.gender` | `person.gender` |
| `data.born` | `person.born_text` |
| `data.image` | `person.image_url` |
| `data.works.Drama[]` | `work.kind = drama` |
| `data.works.Movie[]` | `work.kind = movie` |

`data.works`의 `TV Show`는 읽지 않는다. `data.about`은 요청하지 않은 것이 아니라, 받아도 `person.about`에 넣지 않는다.

출연 항목에서 쓰는 필드:

| 응답 | 저장 |
| --- | --- |
| `slug`의 앞 숫자 | `work.mdl_id` |
| `title` | `work.title` |
| `year` | `work.year` |
| `episodes` | `work.episodes` |
| `rating` | `work.rating` |
| `link` | `work.mdl_url` |
| `role` | `person_work.role` |
| `character` | `person_work.character_name` |

등록 한 번은 이 호출 뒤에, 출연 slug마다 드라마 상세를 추가로 호출한다. 타임아웃은 90초.

### `GET /v2/dramas/{slug}`

작품 상세. 등록 때와, 작품 화면을 열 때 `detail_at`이 비어 있으면 호출한다. 실패하면 그 작품만 건너뛴다. 타임아웃은 60초.

| 응답 | 저장 |
| --- | --- |
| `data.poster` | `work.image_url` |
| `data.synopsis` | `work.synopsis` |
| `data.native_title` | `work.native_title` |
| `data.tags[]` | `work.tags` |

목록의 GL/BL 표시는 이 `tags`를 본다.

| `tags` 값 | 목록 표기 |
| --- | --- |
| `Lesbian Romance` | GL |
| `Gay Romance` | BL |
| `Gay Male Lead` | BL |

### `GET /v2/dramas/{slug}/episodes`

작품 화면의 에피소드 가져오기. 그 작품의 `episode` 행을 응답으로 교체한다. 타임아웃은 60초.

`data.episodes[]`:

| 응답 | 저장 |
| --- | --- |
| `number` | `episode.number`. 정수만 |
| `title` | `episode.title` |
| `air_date` | `episode.air_date` |
| `rating` | `episode.rating` |
| `votes` | `episode.votes` |
| `image` | `episode.image_url` |
| `link` | `episode.mdl_url` |
| `summary` | `episode.summary` |

`summary`는 목록에 있는 짧은 문장이다. 없거나 `null`이면 빈칸이다. 문장 끝 `…`는 응답 그대로다.

### `GET /v2/dramas/{slug}/cast`

작품 화면의 작가·감독 가져오기. `data.cast`는 역할 이름별 배열이다. 읽는 역할은 `Screenwriter & Director`, `Director`, `Screenwriter`뿐이다.

사람 항목:

| 응답 | 저장 |
| --- | --- |
| `slug`의 앞 숫자 | `person.mdl_id` |
| `name` | 프로필 조회 전 이름 |
| `image` | 프로필 이미지가 없을 때의 `person.image_url` |
| `link` | 프로필 `link`가 없을 때의 `person.mdl_url` |
| 배열 키 | `person_work.role` |

각 숫자에 대해 `GET /v2/people/{id}`를 한 번 더 호출해 프로필을 채운다. 이 경로로 생긴 사람은 `person.listed = false`다.

## 2. 영어 위키

MediaWiki API. `https://en.wikipedia.org/w/api.php`. `format=json`.

사람이 검색하고 고른 항목만 `person_source.source = en_wikipedia`에 저장한다. `agent`를 고르면 `company`, `person_company`도 만든다.

호출 간격은 0.6초. 같은 쿼리는 10분 캐시. HTTP 429면 `Retry-After`만큼 기다리고 최대 3번 다시 친다.

### `action=query&list=search`

검색. `srsearch`는 사용자가 입력한 문자열. `srlimit=8`. 제목에 `/`가 있는 결과는 버린다. 인물 문서로 보이는 결과만 최대 4개 보여 준다.

### `action=parse`

`page`는 문서 제목. `prop=wikitext`. `{{Infobox person}}`이 없으면 인물 문서로 보지 않는다.

인포박스에서 읽는 칸: `name`, `birth_name`, `native_name`, `birth_date`, `birth_place`, `height`, `education`, `years_active`, `image`, `agent`.

본문 절: `Career`, `Fashion`, `Ambassadorship`, `Accolades` 또는 `Awards`.

### `action=query&prop=imageinfo`

인포박스 `image` 파일 이름을 `titles=File:{name}`으로 조회한다. `iiprop=url`. 돌아온 URL의 쿼리스트링은 버린다.

## 3. GMMTV Wiki

Fandom MediaWiki API. `https://gmmtv.fandom.com/api.php`. `format=json`.

Sapphic Effect에서 고른 소속사가 GMMTV일 때만 검색 화면을 연다. 고른 항목은 `person_source.source = gmmtv_fandom`에 저장한다.

### `action=opensearch`

`search`는 검색어. `limit=8`. 응답은 배열이고 제목 목록은 두 번째 원소다. 제목에 `/`가 있으면 버린다. 최대 4개.

### `action=parse`

`page`는 문서 제목. `prop=wikitext`. 위키텍스트에 `{{People}}`이 없으면 인물 문서로 보지 않는다.

`{{People}}`에서 읽는 칸: `title1`, `image1` 또는 `image`, `birth_name`, `nickname`, `thai`, `birthday`, `birth_place`, `height`, `weight`, `years_active`, `social_media`.

`== Early Life ==` 본문도 읽는다. `social_media`의 `{{IG}}`, `{{X}}`, `{{TD}}`, `{{TT}}`는 인스타그램, X, Threads, 틱톡 URL로 바꾼다.

이미지 URL은 영어 위키와 같이 `action=query&prop=imageinfo`다.

## 4. Sapphic Effect

공개 JSON API가 아니다. `https://www.sapphiceffect.com` HTML을 읽는다. 타임아웃은 30초.

사람이 고른 항목만 `person_source.source = sapphic_effect`에 저장한다. Ship은 `ship`, `person_ship`에 둔다. 소속사는 `company.sapphic_slug`, `person_company`에 둔다.

### `GET /sitemap.xml`

스타 slug 목록. `<loc>` 안의 `/stars/{slug}`만 모은다. slug는 `[a-z0-9-]+`. 메모리에 6시간 둔다. 검색 API가 없어서, 이 목록과 입력 단어를 점수로 맞춘다.

### `GET /stars/{slug}`

스타 페이지 HTML. 페이지 안 문자열에서 아래를 뽑는다.

| 페이지 안 값 | 저장 |
| --- | --- |
| `<title>`의 `—` 앞 | 표시 이름 |
| `"birthday":"YYYY-MM-DD"` | 선택한 생일 |
| `star-avatars/star-profile/` 이미지 URL | 선택한 이미지 |
| `/companies/{slug}`와 회사 이름 | `company`, `person_company` |
| `/ships/{slug}`, 이름, 아바타 | `ship`, `person_ship` |
| 인스타그램, 틱톡, X URL | 선택한 SNS |
| `Biography & Career Path` 뒤 본문 | 선택한 biography |

시리즈 `/series/`는 읽지 않는다.
