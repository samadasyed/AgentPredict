#include "grpc_server.hpp"
#include "log.hpp"

#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/health_check_service_interface.h>
#include <algorithm>
#include <cctype>
#include <stdexcept>

namespace agentpredict {

// ─── Cursor parsing ───────────────────────────────────────────────────────────

bool ResolveStartCursor(const std::string& cursor_str,
                        uint64_t            tail_cursor,
                        uint64_t&           out_cursor) {
    if (cursor_str.empty()) {
        out_cursor = tail_cursor;  // live tail
        return true;
    }
    // Require a pure run of ASCII digits: rejects signs ("-1", "+5"), leading
    // whitespace ("  5"), hex ("0x10"), and trailing junk ("12abc") — all of
    // which std::stoull would otherwise silently accept or partially parse.
    if (!std::all_of(cursor_str.begin(), cursor_str.end(),
                     [](unsigned char c) { return std::isdigit(c) != 0; })) {
        return false;
    }
    try {
        size_t pos = 0;
        unsigned long long parsed = std::stoull(cursor_str, &pos);
        if (pos != cursor_str.size()) {
            return false;  // defensive; the all-digits check makes this unreachable
        }
        out_cursor = static_cast<uint64_t>(parsed);
        return true;
    } catch (const std::exception&) {
        return false;  // std::out_of_range (overflow) or std::invalid_argument
    }
}

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
            LOG_WARN("[IngestStream] rejected event: " << result.error);
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

    // Resolve the start position from the request cursor.
    //   ""  -> live tail (CurrentCursor() is the next-unwritten index, so only
    //          events that arrive after subscribing are delivered).
    //   "0" -> replay the full retained history (GetSince is INCLUSIVE of the
    //          start cursor and clamps to the oldest retained event), then live.
    uint64_t cursor = 0;
    if (!ResolveStartCursor(req->cursor(), store_->CurrentCursor(), cursor)) {
        return grpc::Status(
            grpc::StatusCode::INVALID_ARGUMENT,
            "cursor must be empty (live tail) or a non-negative integer "
            "ring-buffer position");
    }

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

    // Serve the standard gRPC health-checking protocol (grpc.health.v1.Health).
    // The default service reports SERVING once the server is up, so probes like
    // grpc_health_probe / Kubernetes gRPC liveness checks work out of the box.
    grpc::EnableDefaultHealthCheckService(true);

    grpc::ServerBuilder builder;
    builder.AddListeningPort(address, grpc::InsecureServerCredentials());
    builder.RegisterService(&ingestion_svc);
    builder.RegisterService(&stream_svc);

    // TODO: add TLS credentials and auth interceptor before production deploy.

    auto server = builder.BuildAndStart();
    LOG_INFO("gRPC server listening on " << address);
    server->Wait();
}

}  // namespace agentpredict
