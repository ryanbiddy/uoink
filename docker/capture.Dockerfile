# Uoink with capture: yt-dlp, ffmpeg and CPU faster-whisper, run headless.
# Build:     docker build -f docker/capture.Dockerfile -t uoink-capture .
# MCP stdio: docker run -i --rm -v uoink-data:/home/uoink/.local/share/Uoink uoink-capture
# The pinned Whisper base model (~145 MB) is fetched and SHA-256 checked at
# build time, so transcription needs no download at run time.
FROM python:3.11.17-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM runtime AS build
WORKDIR /build/uoink
COPY . .
# Permissions are final here: a chmod in the runtime stage would copy every
# file of /opt/uoink into a second layer and double the image.
RUN XDG_CACHE_HOME=/tmp/uoink-build-cache \
    sh scripts/linux/install.sh --prefix /opt/uoink --bin-dir /usr/local/bin --python python3 \
    && rm -rf /tmp/uoink-build-cache /build/uoink \
    && /opt/uoink/python/bin/python3 -m compileall -q /opt/uoink \
    && chmod -R a+rX,a-w /opt/uoink

FROM runtime
# The app folder stays root-owned and read-only; Linux keeps all state in
# XDG_DATA_HOME/Uoink.
COPY --from=build /opt/uoink /opt/uoink
RUN ln -s /opt/uoink/uoink /usr/local/bin/uoink \
    && groupadd --gid 10001 uoink \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/uoink --shell /usr/sbin/nologin uoink \
    && install -d -o uoink -g uoink /home/uoink/.local /home/uoink/.local/share \
        /home/uoink/.local/share/Uoink /home/uoink/.cache

ENV HOME=/home/uoink \
    XDG_DATA_HOME=/home/uoink/.local/share \
    UOINK_HEADLESS=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /home/uoink
# No VOLUME: mount one yourself (-v uoink-data:/home/uoink/.local/share/Uoink).
# An image-declared volume would put root-owned parents on a tmpfs HOME.
USER uoink
ENTRYPOINT ["uoink"]
CMD ["mcp"]
