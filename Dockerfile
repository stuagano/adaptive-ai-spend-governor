FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml setup.py README.md gateway-policy.example.yaml ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV GATEWAY_POLICY_STATE_PATH=/data/state.db
ENV GATEWAY_POLICY_SESSION_SECRET=change-me-in-production

VOLUME ["/data"]

EXPOSE 8080

CMD ["gateway-policy", "proxy", "run", "gateway-policy.example.yaml", "--policy-name", "agent-sandbox-session", "--host", "0.0.0.0", "--port", "8080", "--state-path", "/data/state.db"]
