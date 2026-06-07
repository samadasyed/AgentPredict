#include "engine.hpp"

#include <gtest/gtest.h>

#include <cstddef>

using agentpredict::ParseRingCapacity;

TEST(ParseRingCapacity, AcceptsPowerOfTwo) {
    size_t out = 0;
    EXPECT_TRUE(ParseRingCapacity("4096", out));
    EXPECT_EQ(out, 4096u);
}

TEST(ParseRingCapacity, AcceptsOne) {
    size_t out = 0;
    EXPECT_TRUE(ParseRingCapacity("1", out));
    EXPECT_EQ(out, 1u);
}

TEST(ParseRingCapacity, AcceptsUpperBound) {
    size_t out = 0;
    EXPECT_TRUE(ParseRingCapacity("16777216", out));  // 1<<24
    EXPECT_EQ(out, 16777216u);
}

TEST(ParseRingCapacity, RejectsZero) {
    size_t out = 7;
    EXPECT_FALSE(ParseRingCapacity("0", out));
    EXPECT_EQ(out, 7u);  // unchanged
}

TEST(ParseRingCapacity, RejectsNonPowerOfTwo) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("5000", out));
}

TEST(ParseRingCapacity, RejectsAboveUpperBound) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("33554432", out));  // 1<<25 > 1<<24
}

TEST(ParseRingCapacity, RejectsNegative) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("-4096", out));
}

TEST(ParseRingCapacity, RejectsTrailingJunk) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("4096x", out));
}

TEST(ParseRingCapacity, RejectsEmpty) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("", out));
}

TEST(ParseRingCapacity, RejectsOverflow) {
    size_t out = 0;
    EXPECT_FALSE(ParseRingCapacity("99999999999999999999999999", out));
}
