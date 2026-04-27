FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# rag/ imports from agents.generated, so the whole project is needed at build time.
COPY proto/ proto/
COPY agents/ agents/
COPY rag/ rag/

# Generate gRPC Python stubs from proto (rag and agents share agents.generated).
RUN mkdir -p agents/generated && \
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=agents/generated \
        --grpc_python_out=agents/generated \
        proto/events.proto && \
    touch agents/generated/__init__.py && \
    sed -i 's/^import events_pb2 as/from agents.generated import events_pb2 as/' \
        agents/generated/events_pb2_grpc.py

EXPOSE 50052

CMD ["python", "-m", "rag.orchestrator"]
