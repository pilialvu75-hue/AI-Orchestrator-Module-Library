#pragma once
#include <windows.h>
#include <cstdint>
#include <string>
#include <psapi.h>
#pragma comment(lib, "Psapi.lib")
#include <flutter/method_channel.h>
#include <flutter/standard_method_codec.h>

// Original Riserva resource channel, isolated from the runner.
inline void RegisterAivexusResourceTelemetry(flutter::BinaryMessenger* messenger) {
    // Read-only native RAM sampling; available on Windows 7 and newer.
    // The engine messenger owns the registered handler.
    flutter::MethodChannel<flutter::EncodableValue> resources(
        messenger,
        "com.aiorchestrator/resources",
        &flutter::StandardMethodCodec::GetInstance());
    resources.SetMethodCallHandler(
        [previous_total = uint64_t{0}, previous_idle = uint64_t{0},
         has_previous = false](const auto& call, auto result) mutable {
          if (call.method_name() != "sample") {
            result->NotImplemented();
            return;
          }
          MEMORYSTATUSEX memory{};
          memory.dwLength = sizeof(memory);
          if (!GlobalMemoryStatusEx(&memory)) {
            result->Error("memory_unavailable", "GlobalMemoryStatusEx failed");
            return;
          }
          flutter::EncodableMap sample;
          sample[flutter::EncodableValue("availableBytes")] =
              flutter::EncodableValue(static_cast<int64_t>(memory.ullAvailPhys));
          sample[flutter::EncodableValue("totalBytes")] =
              flutter::EncodableValue(static_cast<int64_t>(memory.ullTotalPhys));
          PROCESS_MEMORY_COUNTERS counters{};
          counters.cb = sizeof(counters);
          if (GetProcessMemoryInfo(GetCurrentProcess(), &counters,
                                   sizeof(counters))) {
            sample[flutter::EncodableValue("rssBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(counters.WorkingSetSize));
          }
          FILETIME idle{}, kernel{}, user{};
          if (GetSystemTimes(&idle, &kernel, &user)) {
            const auto ticks = [](const FILETIME& time) -> uint64_t {
              return (static_cast<uint64_t>(time.dwHighDateTime) << 32) |
                     time.dwLowDateTime;
            };
            const uint64_t total = ticks(kernel) + ticks(user);
            const uint64_t idle_ticks = ticks(idle);
            if (has_previous && total > previous_total &&
                idle_ticks >= previous_idle) {
              const auto delta = total - previous_total;
              const auto idle_delta = idle_ticks - previous_idle;
              if (idle_delta <= delta) {
                sample[flutter::EncodableValue("systemCpuPercent")] =
                    flutter::EncodableValue(100.0 * (delta - idle_delta) / delta);
              }
            }
            previous_total = total;
            previous_idle = idle_ticks;
            has_previous = true;
          } else {
            has_previous = false;
          }
          // Measure the executable volume, not an arbitrary drive.
          wchar_t exe[32768]{};
          const DWORD n = GetModuleFileNameW(nullptr, exe, 32768);
          if (n > 0 && n < 32768) {
            const std::wstring full(exe, n);
            const auto slash = full.find_last_of(L"\\\\/");
            if (slash != std::wstring::npos) {
              const auto directory = full.substr(0, slash + 1);
              ULARGE_INTEGER available{}, total{};
              if (GetDiskFreeSpaceExW(directory.c_str(), &available, &total, nullptr)) {
                sample[flutter::EncodableValue("appVolumeFreeBytes")] =
                    flutter::EncodableValue(static_cast<int64_t>(available.QuadPart));
                sample[flutter::EncodableValue("appVolumeTotalBytes")] =
                    flutter::EncodableValue(static_cast<int64_t>(total.QuadPart));
              }
            }
          }
          result->Success(flutter::EncodableValue(sample));
        });
}
