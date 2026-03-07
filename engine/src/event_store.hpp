#pragma once

#include <condition_variable>
#include <cstddef>
#include <functional>
#include <memory>
#include <shared_mutex>
#include <vector>
#include "events.pb.h"

namespace agentpredict {

// Fixed-capacity ring buffer of CanonicalEvents.
// Multiple readers can subscribe with independent cursors.
// Writers never block readers; readers that fall behind lose old events (ring
// wraps). Thread-safe via std::shared_mutex (readers share, writer exclusive).
//
// TODO: benchmark under TSan — if contention is observed, evaluate
//       boost::lockfree::spsc_queue for the single-writer hot path.
class EventStore {
public:
    // capacity: number of events the ring buffer holds.
    // Must be a power of 2 (enforced at construction).
    explicit EventStore(size_t capacity = 4096);
    ~EventStore() = default;

    // Non-copyable, non-movable (holds condition_variable + mutex).
    EventStore(const EventStore&) = delete;
    EventStore& operator=(const EventStore&) = delete;

    // Append a normalized CanonicalEvent.
    // Wakes all waiting subscribers.
    void Append(const CanonicalEvent& event);

    // Returns the current write cursor (monotonically increasing sequence).
    // Readers should store this as their starting position.
    [[nodiscard]] uint64_t CurrentCursor() const;

    // Retrieve all events since `from_cursor` (exclusive).
    // Returns events and the new cursor position.
    struct ReadResult {
        std::vector<CanonicalEvent> events;
        uint64_t                   next_cursor;
    };
    [[nodiscard]] ReadResult GetSince(uint64_t from_cursor) const;

    // Block until new events are available after `cursor`, or `timeout_ms`
    // elapses. Returns true if new events are available.
    bool WaitForNew(uint64_t cursor, int timeout_ms = 1000) const;

    // Total events appended since construction (monotone, never wraps).
    [[nodiscard]] uint64_t TotalIngested() const;

private:
    size_t                         capacity_;
    std::vector<CanonicalEvent>    ring_;
    uint64_t                       write_cursor_{0};  // next slot index (monotone)

    mutable std::shared_mutex      mu_;
    mutable std::condition_variable_any cv_;
};

}  // namespace agentpredict
