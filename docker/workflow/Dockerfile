FROM python:3.14-trixie

ENV NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg jq ripgrep \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g npm@11.18.0 @openai/codex@0.144.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/brand-size-chart

COPY --from=workflow_container_contract README.md pyproject.toml /tmp/workflow-container-contract/
COPY --from=workflow_container_contract workflow_container_contract /tmp/workflow-container-contract/workflow_container_contract
COPY --from=workflow_container_runtime README.md pyproject.toml /tmp/workflow-container-runtime/
COPY --from=workflow_container_runtime workflow_container_runtime /tmp/workflow-container-runtime/workflow_container_runtime
COPY README.md pyproject.toml ./
COPY brand_size_chart ./brand_size_chart

RUN python -m pip install --root-user-action=ignore --no-cache-dir /tmp/workflow-container-contract \
    && python -m pip install --root-user-action=ignore --no-cache-dir /tmp/workflow-container-runtime \
    && python -m pip install --root-user-action=ignore --no-cache-dir .
