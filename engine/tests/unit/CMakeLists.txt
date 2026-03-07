add_executable(engine_unit_tests
  test_normalizer.cpp
  test_event_store.cpp
)

target_link_libraries(engine_unit_tests PRIVATE
  engine_lib
  GTest::gtest
  GTest::gtest_main
  Threads::Threads
)

# Run tests under ThreadSanitizer when TSan build is requested.
# Usage: cmake -DCMAKE_CXX_FLAGS="-fsanitize=thread" ..
include(GoogleTest)
gtest_discover_tests(engine_unit_tests)
