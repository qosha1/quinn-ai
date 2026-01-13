# Development NextJS Dockerfile
FROM node:20-alpine

# Install dependencies for better performance
RUN apk add --no-cache libc6-compat curl

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Default command (can be overridden in docker-compose)
CMD ["npm", "run", "dev"]
