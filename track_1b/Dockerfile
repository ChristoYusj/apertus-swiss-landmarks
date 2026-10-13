# Runtime image used by `make run`. Only lightweight dependencies (no torch, no GPU).
FROM python:3.12-slim AS runtime
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1
WORKDIR /app
COPY pyproject.toml README.md config.json ./
COPY src ./src
RUN pip install --no-cache-dir .
ENTRYPOINT ["landmarks-eval"]
CMD ["--help"]

# Test image: same runtime + pytest + the offline fixture dataset.
FROM runtime AS test
RUN pip install --no-cache-dir "pytest>=8"
COPY tests ./tests
COPY tools ./tools
ENTRYPOINT ["python", "-m", "pytest", "-q", "tests"]
CMD []
