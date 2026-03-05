FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG VITE_DD_APPLICATION_ID
ARG VITE_DD_CLIENT_TOKEN
ARG VITE_DD_SITE
ARG VITE_DD_ENV
ENV VITE_DD_APPLICATION_ID=$VITE_DD_APPLICATION_ID
ENV VITE_DD_CLIENT_TOKEN=$VITE_DD_CLIENT_TOKEN
ENV VITE_DD_SITE=$VITE_DD_SITE
ENV VITE_DD_ENV=$VITE_DD_ENV
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
