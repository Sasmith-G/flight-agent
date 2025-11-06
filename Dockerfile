FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

# Runs the offline demo by default; override CMD and provide .env for live mode:
#   docker run --env-file .env disruption-agent monitor AF 1234 --date 2026-07-10
ENTRYPOINT ["disruption-agent"]
CMD ["demo"]
