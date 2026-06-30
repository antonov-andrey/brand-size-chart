FROM python:3.12-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @openai/codex@0.142.4 @playwright/mcp@0.0.27 \
    && npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/brand-size-chart
