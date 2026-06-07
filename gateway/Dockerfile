FROM python:3.11-slim

WORKDIR /app

# Unbuffered stdout/stderr so uvicorn + subscriber logs stream to `docker logs`.
ENV PYTHONUNBUFFERED=1

# curl is required by the docker-compose healthcheck (curl -f .../health);
# python:3.11-slim does not ship it. Keep update+install+clean in one layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# gateway imports from agents.generated, so proto + agents are needed at build time.
COPY proto/ proto/
COPY agents/ agents/
COPY gateway/ gateway/

# Generate gRPC Python stubs from proto (gateway shares agents.generated).
RUN mkdir -p agents/generated && \
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=agents/generated \
        --grpc_python_out=agents/generated \
        proto/events.proto && \
    touch agents/generated/__init__.py && \
    sed -i 's/^import events_pb2 as/from agents.generated import events_pb2 as/' \
        agents/generated/events_pb2_grpc.py

EXPOSE 8000

CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8000"]
