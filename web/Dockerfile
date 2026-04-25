# syntax=docker/dockerfile:1.7
FROM node:20-alpine

RUN corepack enable

WORKDIR /app/web
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . /app/web

EXPOSE 4321
CMD ["pnpm", "dev"]
