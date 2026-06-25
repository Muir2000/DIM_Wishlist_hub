# 프론트엔드 빌드(Node) → nginx 정적 서빙 + /api 리버스 프록시. 컨텍스트 = 저장소 루트.
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* /app/
# 리눅스 컨테이너에서는 플랫폼 바이너리가 올바르게 설치됨(호스트의 os=linux/ WebDAV 이슈 없음).
RUN npm install --no-audit --no-fund
COPY frontend /app
RUN npm run build

FROM nginx:alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
