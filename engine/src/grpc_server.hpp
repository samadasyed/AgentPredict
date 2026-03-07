#pragma once

#include <memory>
#include <string>
#include "events.grpc.pb.h"
#include "event_store.hpp"
#include "normalizer.hpp"

namespace agentpredict {

// ─── EventIngestion service impl ──────────────────────────────────────────────
// Python agents call IngestEvent / IngestStream.
// Validates via Normalizer, appends to EventStore.

class EventIngestionServiceImpl final
    : public agentpredict::EventIngestion::Service {
public:
    EventIngestionServiceImpl(std::shared_ptr<EventStore>  store,
                               std::shared_ptr<Normalizer> normalizer);

    grpc::Status IngestEvent(grpc::ServerContext*      ctx,
                             const CanonicalEvent*     req,
                             IngestAck*                resp) override;

    grpc::Status IngestStream(grpc::ServerContext*                         ctx,
                              grpc::ServerReader<CanonicalEvent>*           reader,
                              IngestAck*                                    resp) override;

private:
    std::shared_ptr<EventStore>  store_;
    std::shared_ptr<Normalizer>  normalizer_;
};

// ─── EventStream service impl ─────────────────────────────────────────────────
// Gateway subscribes to Subscribe(); server streams normalized events.

class EventStreamServiceImpl final
    : public agentpredict::EventStream::Service {
public:
    explicit EventStreamServiceImpl(std::shared_ptr<EventStore> store);

    grpc::Status Subscribe(grpc::ServerContext*                     ctx,
                           const SubscribeRequest*                  req,
                           grpc::ServerWriter<CanonicalEvent>*      writer) override;

private:
    std::shared_ptr<EventStore> store_;
};

// ─── Server lifecycle ─────────────────────────────────────────────────────────

// Builds and starts the gRPC server on `address` (e.g. "0.0.0.0:50051").
// Blocks until the server shuts down. Call from a dedicated thread or main().
void RunGrpcServer(const std::string&               address,
                   std::shared_ptr<EventStore>      store,
                   std::shared_ptr<Normalizer>      normalizer);

}  // namespace agentpredict
