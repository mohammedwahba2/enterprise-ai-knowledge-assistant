FROM node:22-alpine AS base
RUN corepack enable
WORKDIR /srv

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /srv/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /srv
RUN addgroup -S app -g 10001 && adduser -S app -u 10001 -G app
COPY --from=build --chown=app:app /srv/.next/standalone ./
COPY --from=build --chown=app:app /srv/.next/static ./.next/static
COPY --from=build --chown=app:app /srv/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
