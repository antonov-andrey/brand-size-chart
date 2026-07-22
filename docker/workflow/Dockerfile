ARG WORKFLOW_PLATFORM_BASE_IMAGE=workflow-image-registry.apwid-workflow.svc.cluster.local:5000/apwid-workflow-platform-base:0.7.0
FROM ${WORKFLOW_PLATFORM_BASE_IMAGE}

USER root
WORKDIR /app/brand-size-chart

COPY --chown=1000:1000 . .

RUN python -m pip install --root-user-action=ignore --no-cache-dir ".[test]"

USER 1000:1000
