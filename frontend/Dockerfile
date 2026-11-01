# Multi-stage: build the static site with Node, then serve it with a tiny
# nginx — the built output is just HTML/CSS/JS, no Node needed at runtime.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
# Vite inlines env vars into the built JS at BUILD time, not at container
# start time, so this has to be a build arg, not a runtime environment
# variable (there is no server-side process to read one from later).
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
