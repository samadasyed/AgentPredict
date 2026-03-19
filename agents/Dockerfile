FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto definitions and agent source
COPY proto/ proto/
COPY agents/ agents/

# Generate gRPC Python stubs from proto
RUN mkdir -p agents/generated && \
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=agents/generated \
        --grpc_python_out=agents/generated \
        proto/events.proto && \
    touch agents/generated/__init__.py && \
    sed -i 's/^import events_pb2 as/from agents.generated import events_pb2 as/' \
        agents/generated/events_pb2_grpc.py

# No default CMD — each agent is started via docker-compose command override:
#   polymarket-agent: ["python", "-m", "agents.polymarket.agent"]
#   mma-agent:        ["python", "-m", "agents.mma.agent"]
