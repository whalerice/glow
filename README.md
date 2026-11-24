# glow

태국 엔터 데이터 수집. 현재 구현은 [`storage`](storage)다. 배우의 MyDramaList 숫자 id를 넣으면 kuryana에서 프로필과 출연작을 받아 PostgreSQL에 저장한다.

설계는 [`docs`](docs)에 있다.

- [plan.md](docs/plan.md) — 수집 흐름
- [design.md](docs/design.md) — 테이블, upsert, 환경변수
- [apis.md](docs/apis.md) — 외부 API
- [hub.md](docs/hub.md) — 화면을 hub로 옮기는 구현 계획

## 화면

glow 루트에서 띄운다. hub는 호스트에 열린 `8000`을 본다.

```bash
docker compose up --build -d hub
```

- 화면: http://127.0.0.1:3300/people
- API: http://127.0.0.1:8000/api/people

로컬 화면은 `hub`에서 `pnpm install` 후 `pnpm dev`. http://127.0.0.1:3000/people

## storage 실행

필요: Docker, Docker Compose.

명령은 glow 루트에서 실행한다.

### DB와 API

`web`이 `postgres` healthy 이후 `serve`로 뜬다. 기동 시 스키마를 적용한다. HTML은 없다.

```bash
docker compose up --build web
```

- API: http://localhost:8000/api/people
- PostgreSQL: `localhost:5433`
- 계정: user `glow` / password `glow` / database `glow`

백그라운드:

```bash
docker compose up --build -d web
```

중지. 데이터 볼륨 `pgdata`는 남긴다.

```bash
docker compose down
```

볼륨까지 지우려면 `docker compose down -v`.

### CLI 수집

`app`은 profile `collect`다. `docker compose up`으로는 올라가지 않는다. 한 번 실행하고 컨테이너는 지운다. 의존하는 `postgres`는 같이 기동된다.

인자는 배우 이름이 아니다. MDL 숫자 id다. slug나 주소 전체를 넣으면 맨 앞 숫자만 쓴다.

```bash
docker compose run --rm app register 70935
```

성공하면 `collected`, 실패하면 행을 남기고 `failed`를 출력한 뒤 종료 코드 1이다. 같은 id를 다시 실행하면 새 행이 아니라 재수집이다.

### 환경변수

Compose가 넣는다. 로컬에서 덮어쓸 때만 바꾼다.

| 이름 | 값 |
| --- | --- |
| `DATABASE_URL` | `postgresql://glow:glow@postgres:5432/glow` |
| `KURYANA_BASE_URL` | `https://kuryana.tbdh.app` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `glow` |
