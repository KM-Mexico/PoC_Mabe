FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS source
COPY . .

FROM source AS build
RUN npm run build

FROM dependencies AS test
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*
COPY . .
ENV CHROME_BIN=/usr/bin/chromium
CMD ["npm", "test"]

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/business-case-app/browser /usr/share/nginx/html
EXPOSE 80
