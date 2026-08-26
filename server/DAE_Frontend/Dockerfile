# Build Stage
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Run Stage
FROM nginx:1.25-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# public/ 에 있던 정적 파일(favicon.svg, icons.svg 등)은 원본 권한이 그대로 따라온다.
# 윈도우에서 SFTP로 올린 파일이 700이면 nginx 워커(nginx 사용자)가 못 읽어 403이 난다.
# vite가 생성한 index.html·번들은 644라 정상이므로 "페이지는 뜨는데 favicon만 403"으로 나타난다.
RUN chmod -R a+rX /usr/share/nginx/html

# nginx는 80으로 listen 한다 (compose가 8031:80으로 매핑)
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
