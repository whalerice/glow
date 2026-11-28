# 외부 소스

이 문서가 적는 것은 앱이 실제로 호출하는 주소와, 그 응답에서 저장하는 필드다. 공식 문서 전체를 옮기지 않는다.

공통 `User-Agent`는 `glow-collect/0.1`이다. 위키와 GMMTV 위키, Sapphic Effect는 `HTTP_USER_AGENT`가 있으면 그 값을 쓴다. 위키 기본값은 `glow-collect/0.1 (local actor collection)`이다.

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
| `data.born` | `person.born_text`. `Month D, YYYY`가 맞는 날이면 `YYYY-MM-DD`. 아니면 원문 |
| `data.image` | `person.image_url` |
| `data.works.Drama[]` | `work.kind = drama` |
| `data.works.Movie[]` | `work.kind = movie` |

kuryana는 같은 `Drama` 표가 둘이면 나중 표만 남긴다. 인물 `link` 페이지의 `h5` Drama·Movie 표를 읽어 표를 합친다. 그 페이지를 못 읽으면 kuryana 목록을 쓴다. `TV Show`는 읽지 않는다. 배우 등록의 `data.about`은 `person.about`에 넣지 않는다.

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
| `data.aired` | `work.aired`. `Oct 19, 2024 - Jan 4, 2025`는 `2024-10-19 ~ 2025-01-04`. 둘 다 날짜로 안 풀리면 원문 |
| `data.aired_on` | `work.aired_on`. 배열이면 `, `로 잇는다 |
| `data.content_rating` | `work.content_rating`. 앞의 `13+`, `18+`만. `15+`도 같다. `G - All Ages`는 `전체관람가` |
| `data.original_network[]` | `company` + `company_type`(`org_type` 이름 `방송사`) + `work_company`. 같은 `name_key`면 기존 회사 행을 재사용하고 타입만 추가한다 |

보는 곳은 TMDB다. MDL Where to Watch는 읽지 않는다.

배우 수집이 끝난 작품 중 `work.tmdb_id`가 비어 있으면 TMDB로 찾는다. `drama`는 `GET /3/search/tv`, `movie`는 `GET /3/search/movie`. 제목이 같으면 그 id, 없고 연도가 있으면 첫 결과. 그 id로 `GET /3/{movie|tv}/{id}/watch/providers`. 한국 `KR`, 태국 `TH`만 `work_provider`에 둔다. 나라 응답의 `link`는 `work_provider.url`이다. `flatrate`는 `유료 구독`, `free`는 `Free`, `ads`는 `광고`, `rent`는 `대여`, `buy`는 `구매`. 제공처 `provider_name`은 방송사와 같이 `name_key`로 `company`에 넣는다. 없으면 만들고, 있으면 재사용한다. `logo_path`는 `https://image.tmdb.org/t/p/original`을 붙인 전체 주소로, `logo_url`이 비어 있을 때만 넣는다. `company_type`에는 `배급사`를 추가하고 기존 타입은 지우지 않는다. `work_company`는 건드리지 않는다. 이미 id가 있으면 수집 때 덮지 않는다. 작품 화면에서 id와 `movie`/`tv`를 고치고 다시 가져오기를 누르면 그 값으로 제공처를 교체한다. 토큰은 `tmdb_access_token_auth`. 실패해도 배우 수집은 유지한다.

같은 작품 id로 `GET /3/{movie|tv}/{id}?append_to_response=keywords,translations,images,videos&include_video_language=en,th,ko,null`도 읽는다. 응답 `homepage`가 `http://` 또는 `https://`면 `work.homepage`에 두고, 아니면 비운다. `videos.results`에서 `site=YouTube`인 `Teaser`를 우선하고 없으면 `Trailer`를 고른다. `official` 우선, 같으면 `published_at` 최신. `key`로 `work.teaser_url`=`https://www.youtube.com/watch?v={key}`. 없으면 비운다. 작품 상세에 새 창 링크로 보인다. `networks[]`와 `production_companies[]`의 `name`이 기존 `company.name`과 같으면, 비어 있는 `logo_url`과 `homepage`만 채운다. 로고는 `https://image.tmdb.org/t/p/original` 뒤에 `logo_path`를 붙인 전체 주소다. 홈페이지는 목록에 없으므로 그때만 `GET /3/network/{id}` 또는 `GET /3/company/{id}`를 읽고, 그 id는 저장하지 않는다. `networks`에 있으면 `방송사`, `production_companies`에 있으면 `제작사`와 `배급사`를 `company_type`에 추가한다. 없는 회사 행은 만들지 않고, 이미 있는 로고·홈페이지·타입은 유지한다.

목록의 GL/BL 표시는 이 `tags`를 본다.

| `tags` 값 | 목록 표기 |
| --- | --- |
| `Lesbian Romance` | GL |
| `Gay Romance` | BL |
| `Gay Male Lead` | BL |

### `GET /v2/dramas/{slug}/episodes`

작품 화면의 에피소드 가져오기. `kind`가 `movie`인 상세에는 에피소드 칸을 두지 않는다. 그 작품의 `episode` 행을 응답으로 교체한다. 타임아웃은 60초.

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

각 숫자에 대해 `GET /v2/people/{id}`를 한 번 더 호출해 프로필을 채운다. `data.about`은 `person.about`이다. 값이 `Add Biography`면 비운다. `data.born`은 배우와 같이 `person.born_text`로 맞춘다. 이어서 인물 `link` HTML의 Details에서 Instagram, Twitter, X, TikTok, Facebook, YouTube, Weibo, Threads가 있으면 `person.socials`에 `{kind, url}`로 넣는다. 그 줄이 없으면 기존 `socials`를 유지한다. 역할은 `Director` → `person_role` `d`, `Screenwriter` → `w`, `Screenwriter & Director` → `d`와 `w`. 그 사람이 이미 배우(`a`)면 프로필은 덮지 않고 역할과 `person_work`만 추가한다.

## 2. 위키

`wikipedia-api`. 주소는 `https://{lang}.wikipedia.org/w/api.php`. 저장 소스 키는 `en_wikipedia`다. `external_key`는 영어면 문서 제목, 다른 언어면 `fr:제목`처럼 언어를 붙인다.

사람이 검색하고 고른 항목만 저장한다. `agent`를 고르면 `company`, `person_company`도 만든다.

429는 라이브러리가 다시 친다. 그래도 막히면 검색을 멈춘다.

### 검색

검색어가 `https://fr.wikipedia.org/wiki/Lorena_Schuett`처럼 위키 주소면 그 언어와 제목만 연다. 아니면 영어를 먼저 찾고, 인물 문서가 없으면 프랑스어를 찾는다. 태국어·인도네시아어·중국어는 찾지 않는다. 제목에 `/`가 있는 결과는 버린다. 인물 문서로 보이는 결과만 최대 4개 보여 준다.

### `wiki.page`와 `action=parse`

`wiki.page`로 문서가 있는지 보고, 주소는 `page.fullurl`이다. 인포박스는 요약문에 없으므로 같은 언어 클라이언트로 `action=parse`, `prop=wikitext`를 읽는다. `{{Infobox person}}`, `{{Infobox pageant titleholder}}`, `{{Infobox Biographie2}}`가 없으면 인물 문서로 보지 않는다.

인포박스에서 읽는 칸: `name`, `birth_name`, `native_name`, `birth_date`, `birth_place`, `height`, `education`, `years_active`, `image`, `agent`. 프랑스어 칸은 같은 이름으로 바꾼다. `date de naissance`, `lieu de naissance`, `nom de naissance`, `nom`, `université / formation`, `années d'activité`, `taille`. `native_name`이 없고 `légende`에 태국어가 있으면 그 문자열을 쓴다. `agent`와 `agence`를 읽고, `présent`는 `present`로 둔다.

생일이 인포박스에 없으면 첫 절 앞 리드의 생일을 쓴다. 경력 본문은 `Career`, 없으면 `Carrière`, 없으면 `Biographie`. 그 밖은 `Fashion`, `Ambassadorship`, `Accolades` 또는 `Awards`. 절 제목의 악센트는 접고 비교한다.

### 이미지

인포박스 `image` 파일과 같은 이름을 `page.images`에서 찾는다. URL의 쿼리스트링은 버린다.

## 3. GMMTV Wiki

Fandom MediaWiki API. `https://gmmtv.fandom.com/api.php`. `format=json`.

Sapphic Effect에서 고른 소속사가 GMMTV일 때만 검색 화면을 연다. 고른 항목은 `person_source.source = gmmtv_fandom`에 저장한다.

### `action=opensearch`

`search`는 검색어. `limit=8`. 응답은 배열이고 제목 목록은 두 번째 원소다. 제목에 `/`가 있으면 버린다. 최대 4개.

### `action=parse`

`page`는 문서 제목. `prop=wikitext`. 위키텍스트에 `{{People}}`이 없으면 인물 문서로 보지 않는다.

`{{People}}`에서 읽는 칸: `title1`, `image1` 또는 `image`, `birth_name`, `nickname`, `thai`, `birthday`, `birth_place`, `height`, `weight`, `years_active`, `social_media`.

`== Early Life ==` 본문도 읽는다. `social_media`의 `{{IG}}`, `{{X}}`, `{{TD}}`, `{{TT}}`는 인스타그램, X, Threads, 틱톡 URL로 바꾼다.

이미지 URL은 `action=query&prop=imageinfo`다. `titles=File:{name}`. 쿼리스트링은 버린다.

## 4. Sapphic Effect

공개 JSON API가 아니다. `https://www.sapphiceffect.com` HTML을 읽는다. 타임아웃은 30초.

사람이 고른 항목만 `person_source.source = sapphic_effect`에 저장한다. Ship은 `ship`, `person_ship`에 둔다. 소속사는 `company.sapphic_slug`, `person_company`에 두고 `company_type`에 `엔터테이먼트`를 추가한다. 이미 있는 타입은 지우지 않는다.

### `GET /sitemap.xml`

스타 slug 목록. `<loc>` 안의 `/stars/{slug}`만 모은다. slug는 `[a-z0-9-]+`. 메모리에 6시간 둔다. 검색 API가 없어서, 이 목록과 입력 단어를 점수로 맞춘다.

### `GET /stars/{slug}`

스타 페이지 HTML. 페이지 안 문자열에서 아래를 뽑는다.

| 페이지 안 값 | 저장 |
| --- | --- |
| `<title>`의 `—` 앞 | 표시 이름 |
| `"birthday":"YYYY-MM-DD"` | 선택한 생일 |
| `star-avatars/star-profile/` 이미지 URL | 선택한 이미지 |
| `/companies/{slug}`와 회사 이름 | `company`, `person_company`, `company_type`(`엔터테이먼트`) |
| `/ships/{slug}`, 이름, 아바타 | `ship`, `person_ship` |
| 인스타그램, 틱톡, X URL | 선택한 SNS |
| `Biography & Education` Read more 전문 | 선택한 biography. 예전 제목 `Biography & Career Path`도 읽는다 |

회사 로고는 작품 TMDB의 `networks`와 `production_companies`에서 이름이 같을 때, 그리고 시청처 `logo_path`로 `company.logo_url`에 넣는다. 비어 있을 때만 채운다. Sapphic Effect 회사 페이지에서는 로고를 읽지 않는다.

시리즈 `/series/`는 읽지 않는다.
