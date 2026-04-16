FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ .
RUN npx expo export --platform web

# ── Backend + serve frontend ──────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache bust: v3.0 Liquid Glass (2026-04-12)
# Copy backend code
COPY backend/ .

# Copy pre-built frontend into /app/static
COPY --from=frontend-build /frontend/dist /app/static

# Copy SF Pro Display fonts to static directory (not included by Expo web export)
COPY --from=frontend-build /frontend/src/assets/fonts/SFProDisplay-Regular.otf /app/static/assets/fonts/
COPY --from=frontend-build /frontend/src/assets/fonts/SFProDisplay-Light.otf /app/static/assets/fonts/
COPY --from=frontend-build /frontend/src/assets/fonts/SFProDisplay-Medium.otf /app/static/assets/fonts/
COPY --from=frontend-build /frontend/src/assets/fonts/SFProDisplay-Semibold.otf /app/static/assets/fonts/
COPY --from=frontend-build /frontend/src/assets/fonts/SFProDisplay-Bold.otf /app/static/assets/fonts/

# Create directories
RUN mkdir -p logs data

EXPOSE 8000

CMD ["python", "main.py"]
