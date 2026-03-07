#include "event_store.hpp"

#include <cassert>
#include <chrono>
#include <stdexcept>

namespace agentpredict {

EventStore::EventStore(size_t capacity) : capacity_(capacity), ring_(capacity) {
    if (capacity == 0 || (capacity & (capacity - 1)) != 0) {
        throw std::invalid_argument("EventStore capacity must be a power of 2");
    }
}

// ─── Write ────────────────────────────────────────────────────────────────────

void EventStore::Append(const CanonicalEvent& event) {
    {
        std::unique_lock lock(mu_);
        size_t slot = write_cursor_ & (capacity_ - 1);  // fast modulo (power-of-2)
        ring_[slot] = event;
        ++write_cursor_;
    }
    cv_.notify_all();
}

// ─── Read ─────────────────────────────────────────────────────────────────────

uint64_t EventStore::CurrentCursor() const {
    std::shared_lock lock(mu_);
    return write_cursor_;
}

uint64_t EventStore::TotalIngested() const {
    std::shared_lock lock(mu_);
    return write_cursor_;
}

EventStore::ReadResult EventStore::GetSince(uint64_t from_cursor) const {
    std::shared_lock lock(mu_);

    ReadResult result;
    result.next_cursor = write_cursor_;

    if (from_cursor >= write_cursor_) {
        // No new events.
        return result;
    }

    // Protect against readers that have fallen more than `capacity_` events
    // behind — the ring has overwritten their data.
    uint64_t oldest_available = (write_cursor_ > capacity_)
                                    ? (write_cursor_ - capacity_)
                                    : 0;
    uint64_t effective_start = std::max(from_cursor, oldest_available);

    result.events.reserve(write_cursor_ - effective_start);
    for (uint64_t cursor = effective_start; cursor < write_cursor_; ++cursor) {
        size_t slot = cursor & (capacity_ - 1);
        result.events.push_back(ring_[slot]);
    }

    return result;
}

bool EventStore::WaitForNew(uint64_t cursor, int timeout_ms) const {
    std::shared_lock lock(mu_);
    return cv_.wait_for(
        lock,
        std::chrono::milliseconds(timeout_ms),
        [this, cursor] { return write_cursor_ > cursor; }
    );
}

}  // namespace agentpredict
