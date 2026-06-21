FROM node:22-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
RUN npm install -g serve \
    && addgroup -g 1001 -S nodejs \
    && adduser -S nodeuser -u 1001 -G nodejs
WORKDIR /app
COPY --from=builder /app/dist ./dist
USER nodeuser
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD wget -qO- http://localhost:3000/ || exit 1
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
