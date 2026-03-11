FROM node:20-alpine
RUN apk add --no-cache curl openssl
WORKDIR /app
COPY package.json .
RUN npm install
COPY prisma/ ./prisma/
RUN npx prisma generate
COPY tsconfig.json .
COPY src/ ./src/
RUN npm run build
EXPOSE 3000
CMD ["sh", "-c", "npx prisma db push --skip-generate && node dist/index.js"]
