FROM node:22-slim

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@12.21.0 --activate

COPY . .
RUN pnpm install --frozen-lockfile && pnpm build

ENV HOST=0.0.0.0
ENV PORT=3000
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
