# hub

화면. Nuxt + Nuxt UI + Tailwind.

glow 루트에서 띄운다. API는 호스트에 열린 `8000`이다.

```bash
docker compose up --build -d hub
```

http://127.0.0.1:3300/people

로컬 개발은 storage API가 `8000`에 떠 있어야 한다.

```bash
pnpm install
pnpm dev
```

http://127.0.0.1:3000/people
