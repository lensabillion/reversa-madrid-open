# The explorer image. The first stage installs exactly what package-lock.json records
# (under frontend/.npmrc: no install scripts) and runs `next build` with
# `output: "standalone"`, which traces the files each route needs. The second stage
# carries only that trace, so no node_modules and no source ship in the running image.
#
# Base images are pinned by digest (SUPPLY-CHAIN-SECURITY.md rule 4 applied to images);
# the tag matches frontend/.nvmrc.
FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS builder

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /build

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

# next.config.ts reads INFLUENCE_API_URL when the config is loaded, which for a
# standalone build is at build time: the proxy target is baked into server.js. Compose
# passes the backend service's address; the default suits the compose network too.
ARG INFLUENCE_API_URL=http://backend:8000
ENV INFLUENCE_API_URL=$INFLUENCE_API_URL
RUN npm run build

FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app

# server.js serves .next/static itself once the folder sits beside it (Next.js "output"
# reference); the image has no public/ directory to copy.
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static

USER node
EXPOSE 3000

# The explorer's shell renders without the API, so this proves the server, not the proxy;
# `make check-containers` probes the proxy path separately.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/lineage').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]

CMD ["node", "server.js"]
