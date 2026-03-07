#include "grpc_server.hpp"

#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <iostream>

namespace agentpredict {

// ─── EventIngestionServiceImpl ────────────────────────────────────────────────

EventIngestionServiceImpl::EventIngestionServiceImpl(
    std::shared_ptr<EventStore> store,
    std::shared_ptr<Normalizer> normalizer)
    : store_(std::move(store)), normalizer_(std::move(normalizer)) {}

grpc::Status EventIngestionServiceImpl::IngestEvent(
    grpc::ServerContext* /*ctx*/,
    const CanonicalEvent* req,
    IngestAck* resp) {

    CanonicalEvent mutable_event = *req;
    auto result = normalizer_->Normalize(mutable_event);

    resp->set_event_id(mutable_event.event_id());
    resp->set_accepted(result.ok);
    resp->set_reason(result.error);

    if (result.ok) {
        store_->Append(mutable_event);
    }

    return grpc::Status::OK;
}

grpc::Status EventIngestionServiceImpl::IngestStream(
    grpc::ServerContext* /*ctx*/,
    grpc::ServerReader<CanonicalEvent>* reader,
    IngestAck* resp) {

    CanonicalEvent event;
    uint32_t accepted = 0;
    uint32_t rejected = 0;

    while (reader->Read(&event)) {
        auto result = normalizer_->Normalize(event);
        if (result.ok) {
            store_->Append(event);
            ++accepted;
        } else {
            ++rejected;
            std::cerr << "[IngestStream] rejected event: " << result.error << '\n';
        }
    }

    // Final ACK summarises the stream.
    resp->set_accepted(rejected == 0);
    resp->set_reason("accepted=" + std::to_string(accepted) +
                     " rejected=" + std::to_string(rejected));
    return grpc::Status::OK;
}

// ─── EventStreamServiceImpl ───────────────────────────────────────────────────

EventStreamServiceImpl::EventStreamServiceImpl(
    std::shared_ptr<EventStore> store)
    : store_(std::move(store)) {}

grpc::Status EventStreamServiceImpl::Subscribe(
    grpc::ServerContext* ctx,
    const SubscribeRequest* req,
    grpc::ServerWriter<CanonicalEvent>* writer) {

    // TODO: parse req->cursor() as uint64 if non-empty for resume support.
    // For now, start from the current tail.
    uint64_t cursor = store_->CurrentCursor();

    while (!ctx->IsCancelled()) {
        // Block until new events or timeout (avoids busy-wait).
        store_->WaitForNew(cursor, /*timeout_ms=*/500);

        auto [events, next_cursor] = store_->GetSince(cursor);
        cursor = next_cursor;

        for (const auto& event : events) {
            // Apply source filter if set.
            if (req->source_filter() != SOURCE_UNKNOWN &&
                event.source() != req->source_filter()) {
                continue;
            }
            if (!writer->Write(event)) {
                // Client disconnected.
                return grpc::Status::OK;
            }
        }
    }

    return grpc::Status::OK;
}

// ─── Server lifecycle ─────────────────────────────────────────────────────────

void RunGrpcServer(const std::string&          address,
                   std::shared_ptr<EventStore> store,
                   std::shared_ptr<Normalizer> normalizer) {
    EventIngestionServiceImpl ingestion_svc(store, normalizer);
    EventStreamServiceImpl    stream_svc(store);

    grpc::ServerBuilder builder;
    builder.AddListeningPort(address, grpc::InsecureServerCredentials());
    builder.RegisterService(&ingestion_svc);
    builder.RegisterService(&stream_svc);

    // TODO: add TLS credentials and auth interceptor before production deploy.

    auto server = builder.BuildAndStart();
    std::cout << "[engine] gRPC server listening on " << address << '\n';
    server->Wait();
}

}  // namespace agentpredict
