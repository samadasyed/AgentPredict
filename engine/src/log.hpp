#pragma once

// Minimal leveled logger for the engine.
//
// Level is read once from ENGINE_LOG_LEVEL (DEBUG|INFO|WARN|ERROR; default INFO).
// Every line is flushed (std::endl) so logs appear immediately under
// `docker logs` / non-TTY stdout, and a mutex prevents interleaving across the
// gRPC thread pool. Header-only — no CMake changes needed.
//
// Usage:  LOG_INFO("listening on " << addr);

#include <cstdlib>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>

namespace agentpredict::log {

enum class Level { kDebug = 0, kInfo = 1, kWarn = 2, kError = 3 };

inline Level ParseLevel(std::string_view s) {
    if (s == "DEBUG" || s == "debug") return Level::kDebug;
    if (s == "WARN" || s == "warn") return Level::kWarn;
    if (s == "ERROR" || s == "error") return Level::kError;
    return Level::kInfo;  // default / unrecognized
}

inline Level CurrentLevel() {
    static const Level level = [] {
        const char* env = std::getenv("ENGINE_LOG_LEVEL");
        return env != nullptr ? ParseLevel(env) : Level::kInfo;
    }();
    return level;
}

inline const char* Tag(Level l) {
    switch (l) {
        case Level::kDebug: return "DEBUG";
        case Level::kInfo: return "INFO";
        case Level::kWarn: return "WARN";
        case Level::kError: return "ERROR";
    }
    return "INFO";
}

inline void Write(Level l, const std::string& msg) {
    static std::mutex mu;
    std::ostream& os = (l >= Level::kWarn) ? std::cerr : std::cout;
    std::lock_guard<std::mutex> lk(mu);
    os << "[engine][" << Tag(l) << "] " << msg << std::endl;  // endl flushes
}

}  // namespace agentpredict::log

#define AP_LOG(LEVEL, EXPR)                                                     \
    do {                                                                       \
        if (static_cast<int>(LEVEL) >=                                         \
            static_cast<int>(::agentpredict::log::CurrentLevel())) {           \
            std::ostringstream _ap_oss;                                        \
            _ap_oss << EXPR;                                                   \
            ::agentpredict::log::Write(LEVEL, _ap_oss.str());                  \
        }                                                                      \
    } while (0)

#define LOG_DEBUG(EXPR) AP_LOG(::agentpredict::log::Level::kDebug, EXPR)
#define LOG_INFO(EXPR) AP_LOG(::agentpredict::log::Level::kInfo, EXPR)
#define LOG_WARN(EXPR) AP_LOG(::agentpredict::log::Level::kWarn, EXPR)
#define LOG_ERROR(EXPR) AP_LOG(::agentpredict::log::Level::kError, EXPR)
