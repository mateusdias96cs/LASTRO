# Imagem do frontend. Mesmo critério da imagem da API: multi-stage, não-root,
# versão fixada.
#
# A URL da API entra em BUILD, não em runtime. Next embute `NEXT_PUBLIC_*` no
# bundle que vai para o navegador, então mudá-la depois exige reconstruir a
# imagem. Isso é limitação do Next, não escolha nossa. Vale saber antes de
# tentar trocar a URL por variável do Container App e não entender por que não
# surtiu efeito.
FROM node:22.13.1-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts || npm install --omit=dev --ignore-scripts

FROM node:22.13.1-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22.13.1-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
# UID numérico, não nome: é o que o PodSecurityStandard `restricted` valida:
# a mesma regra que este sistema audita nos arquivos dos outros.
RUN useradd --system --uid 10001 --no-create-home web
COPY --from=build --chown=10001:10001 /app/.next/standalone ./
COPY --from=build --chown=10001:10001 /app/.next/static ./.next/static
COPY --from=build --chown=10001:10001 /app/public ./public
USER 10001
EXPOSE 3000
CMD ["node", "server.js"]
