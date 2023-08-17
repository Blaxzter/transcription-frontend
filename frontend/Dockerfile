# Build env
FROM node:lts-alpine as build-npm-stage

WORKDIR /text_transcribe

COPY package*.json ./

RUN npm install

COPY vite.config.js ./
COPY index.html ./
COPY public ./public
COPY src ./src

RUN npm run build

#RUN npm install -g lite-server
#EXPOSE 80
#CMD ["lite-server", "--baseDir", "/respeak-expert-frontend/dist", "--port", "80"]


# Run env
FROM nginx:stable-alpine
COPY --from=build-npm-stage /text_transcribe/dist /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["nginx", "-g", "daemon off;"]
