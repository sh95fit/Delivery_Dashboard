FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_MAPS_API_KEY=""
ENV VITE_MAPS_API_KEY=$VITE_MAPS_API_KEY

COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
