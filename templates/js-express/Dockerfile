FROM node:20-alpine
RUN apk add --no-cache curl openssl
WORKDIR /app
COPY package.json .
RUN npm install
COPY prisma/ ./prisma/
RUN npx prisma generate
COPY src/ ./src/
EXPOSE 3000
CMD ["sh", "-c", "npx prisma db push --skip-generate && node src/index.js"]
