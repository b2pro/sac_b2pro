# Estagio de build: precisa das devDependencies (vite, typescript), por isso
# instala tudo. O projeto usa pnpm -- nao existe package-lock.json, e `npm ci`
# falharia.
FROM node:24-alpine AS build
WORKDIR /app
RUN npm install -g pnpm@9.15.0
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Imagem final: so nginx e os arquivos estaticos. Nada de Node em producao.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
