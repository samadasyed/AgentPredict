#include "grpc_server.hpp"

#include <gtest/gtest.h>

#include <cstdint>

using agentpredict::ResolveStartCursor;

// Empty cursor → start at the live tail (the supplied tail_cursor).
TEST(ResolveStartCursor, EmptyUsesTail) {
    uint64_t out = 999;
    EXPECT_TRUE(ResolveStartCursor("", 42, out));
    EXPECT_EQ(out, 42u);
}

// "0" → replay from the start of the retained history.
TEST(ResolveStartCursor, ZeroReplaysFromStart) {
    uint64_t out = 999;
    EXPECT_TRUE(ResolveStartCursor("0", 42, out));
    EXPECT_EQ(out, 0u);
}

TEST(ResolveStartCursor, ParsesValidNumber) {
    uint64_t out = 0;
    EXPECT_TRUE(ResolveStartCursor("12345", 7, out));
    EXPECT_EQ(out, 12345u);
}

TEST(ResolveStartCursor, ParsesUint64Max) {
    uint64_t out = 0;
    EXPECT_TRUE(ResolveStartCursor("18446744073709551615", 0, out));
    EXPECT_EQ(out, 18446744073709551615ull);
}

// std::stoull would silently accept these — the helper must reject them.
TEST(ResolveStartCursor, RejectsNegative) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("-1", 7, out));
}

TEST(ResolveStartCursor, RejectsPlusSign) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("+5", 7, out));
}

TEST(ResolveStartCursor, RejectsLeadingWhitespace) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("  5", 7, out));
}

TEST(ResolveStartCursor, RejectsTrailingJunk) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("12abc", 7, out));
}

TEST(ResolveStartCursor, RejectsHexLiteral) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("0x10", 7, out));
}

TEST(ResolveStartCursor, RejectsNonNumeric) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("abc", 7, out));
}

TEST(ResolveStartCursor, RejectsOverflow) {
    uint64_t out = 0;
    EXPECT_FALSE(ResolveStartCursor("99999999999999999999999999", 7, out));
}

// On rejection the out-parameter must be left untouched.
TEST(ResolveStartCursor, LeavesOutUnchangedOnReject) {
    uint64_t out = 123;
    EXPECT_FALSE(ResolveStartCursor("-1", 7, out));
    EXPECT_EQ(out, 123u);
}
