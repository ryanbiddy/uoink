FROM python:3.11.17-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp/uoink/home \
    XDG_DATA_HOME=/tmp/uoink/xdg \
    LOCALAPPDATA=/tmp/uoink/appdata \
    UOINK_ISOLATED_PROFILE=/tmp/uoink/profile \
    UOINK_ISOLATED_APP_DIR=/tmp/uoink/app \
    UOINK_ISOLATED_PORT=5180 \
    UOINK_OUTPUT_DIR=/tmp/uoink/profile/output \
    UOINK_USAGE_ENDPOINT="" \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app
COPY requirements-mcp.txt ./
RUN python -m pip install --no-cache-dir -r requirements-mcp.txt

COPY *.py VERSION topics.json ./
COPY helper/__init__.py helper/_version.py ./helper/
COPY uoink_core/ ./uoink_core/
COPY migrations/ ./migrations/
COPY scripts/run_mcp_container.py scripts/smoke_mcp_container.py ./scripts/

USER 65532:65532
ENTRYPOINT ["python", "-B", "/app/scripts/run_mcp_container.py"]
