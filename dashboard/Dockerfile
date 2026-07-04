# syntax=docker/dockerfile:1

# ---- Stage 1: build the Vite bundle -----------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first for better layer caching.
COPY package*.json ./
RUN npm ci || npm install

# Build the app. VITE_API_BASE can be baked at build time; if omitted the app
# defaults to http://localhost:8000 and falls back to bundled sample data.
COPY . .
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ---- Stage 2: serve static files with nginx on port 80 ----------------------
FROM nginx:1.27-alpine AS serve
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
