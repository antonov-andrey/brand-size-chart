FROM python:3.14-bookworm

ENV NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg jq ripgrep \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g npm@11.18.0 @openai/codex@0.142.4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/brand-size-chart

COPY README.md pyproject.toml ./
COPY brand_size_chart ./brand_size_chart

RUN python -m pip install --root-user-action=ignore --no-cache-dir .
