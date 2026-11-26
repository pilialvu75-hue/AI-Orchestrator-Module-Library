import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';

/// Unknown readings stay null. RSS, native heap and system RAM are distinct;
/// they must never be added together as an estimate of app memory.
class ResourceSample {
  ResourceSample(Map<Object?, Object?> data, {DateTime? timestamp})
      : timestamp = timestamp ?? DateTime.now(),
        availableBytes = _number(data['availableBytes']),
        totalBytes = _number(data['totalBytes']),
        thresholdBytes = _number(data['thresholdBytes']),
        rssBytes = _number(data['rssBytes']),
        systemCpuPercent = _percent(data['systemCpuPercent']),
        processCpuCorePercent = _corePercent(data['processCpuCorePercent']),
        appVolumeFreeBytes = _number(data['appVolumeFreeBytes']),
        appVolumeTotalBytes = _number(data['appVolumeTotalBytes']),
        nativeHeapBytes = _number(data['nativeHeapBytes']),
        batteryTemperatureDeciC = _number(data['batteryTempDeciC']),
        deviceManufacturer = _text(data['deviceManufacturer']),
        deviceModel = _text(data['deviceModel']),
        deviceName = _text(data['deviceName']),
        sdkInt = _number(data['sdkInt']),
        primaryAbi = _text(data['primaryAbi']),
        lowMemory = data['lowMemory'] == true,
        trimLevel = _number(data['trimLevel']) ?? 0;

  final DateTime timestamp;
  final double? systemCpuPercent, processCpuCorePercent;
  final int? availableBytes,
      totalBytes,
      thresholdBytes,
      rssBytes,
      nativeHeapBytes,
      batteryTemperatureDeciC,
      sdkInt, appVolumeFreeBytes, appVolumeTotalBytes;
  final String? deviceManufacturer, deviceModel, deviceName, primaryAbi;
  final bool lowMemory;
  final int trimLevel;

  /// Read-only Android battery temperature proxy in degrees Celsius.
  ///
  /// This is not SoC junction temperature and must not be presented as one.
  double? get batteryTemperatureC => batteryTemperatureDeciC == null
      ? null
      : batteryTemperatureDeciC! / 10.0;
  static int? _number(Object? value) =>
      value is num && value.isFinite && value >= 0 ? value.toInt() : null;

  static double? _percent(Object? value) =>
      value is num && value.isFinite && value >= 0 && value <= 100
          ? value.toDouble()
          : null;

  static double? _corePercent(Object? value) =>
      value is num && value.isFinite && value >= 0 && value <= 409600
          ? value.toDouble() : null;

  static String? _text(Object? value) {
    final text = value is String ? value.trim() : '';
    return text.isEmpty ? null : text;
  }

  String get benchmarkHardwareProfile => <String>[
        'android',
        'manufacturer:${deviceManufacturer ?? 'unknown'}',
        'model:${deviceModel ?? 'unknown'}',
        'device:${deviceName ?? 'unknown'}',
        'sdk:${sdkInt ?? -1}',
        'abi:${primaryAbi ?? 'unknown'}',
        'ram:${totalBytes ?? -1}',
      ].join('|');

  // UI_HIDDEN=20 and background levels are lifecycle signals, not evidence
  // of foreground RAM pressure. Android 14+ may omit trim notifications.
  bool get critical =>
      lowMemory ||
      trimLevel == 15 ||
      (availableBytes != null &&
          thresholdBytes != null &&
          availableBytes! <= thresholdBytes!);
  bool get pressured =>
      critical ||
      trimLevel == 5 ||
      trimLevel == 10 ||
      (availableBytes != null &&
          thresholdBytes != null &&
          availableBytes! < thresholdBytes! + 512 * 1024 * 1024);
  String get pressure => critical
      ? 'critical'
      : pressured
          ? 'high'
          : availableBytes != null && thresholdBytes != null
              ? 'normal'
              : 'unknown';
}

int minResourceGenerationLimit(int context) => (context ~/ 2).clamp(1, 2048);

class ResourceProfile {
  const ResourceProfile(this.context, this.batch, this.microBatch, this.reason);
  final int context, batch, microBatch;
  final String reason;
  static ResourceProfile select(
    ResourceSample? sample, {
    required bool phi,
    int requestedGpuLayers = 0,
    bool memoryConstrained = false,
  }) {
    // Keep the learned budget after unloading restores free system RAM.
    // Phi has a large KV cache: shrink it without disabling GPU offload.
    if (phi && memoryConstrained) {
      return const ResourceProfile(1536, 64, 16, 'phi_memory_recovery');
    }
    if (sample?.pressured == true) {
      return const ResourceProfile(2048, 128, 32, 'pressure');
    }
    if (phi) {
      // Aggressive GPU offload on Phi leaves substantially less free RAM.
      // Start with the same micro-batch used under pressure so a healthy
      // cached session does not have to be torn down only to shrink 64 -> 32.
      if (requestedGpuLayers >= 32) {
        return const ResourceProfile(2048, 128, 32, 'phi_gpu_conservative');
      }
      return const ResourceProfile(2048, 128, 64, 'phi_conservative');
    }
    // Keep a smaller KV/compute allocation on phones with at most 8 GiB.
    // Free RAM alone can look healthy before weights become resident.
    final total = sample?.totalBytes;
    if (total != null && total > 0 && total <= 8 * 1024 * 1024 * 1024) {
      // Current main already uses pressure-compatible geometry for 3B-class
      // non-Phi models on <=8 GiB phones. Keep that safety baseline and only
      // refine the diagnostic reason when aggressive Vulkan offload is active.
      return ResourceProfile(
        2048,
        128,
        32,
        requestedGpuLayers >= 32
            ? 'device_gpu_conservative'
            : 'device_memory_conservative',
      );
    }
    return const ResourceProfile(4096, 512, 128, 'baseline');
  }
}

/// Sampling is owned by active inference and visible panels, not by a route.
/// At most one platform request is in flight. The ring and persisted event
/// stream are bounded; no network operation is performed by this service.
class ResourceMonitor extends ChangeNotifier {
  ResourceMonitor({
    Future<Map<Object?, Object?>?> Function()? sampler,
    void Function(String)? logger,
  })  : _sampler = sampler ?? _platformSample,
        _logger = logger ?? RuntimeEventLog.instance.emit;
  static final instance = ResourceMonitor();
  static const _channel = MethodChannel('com.aiorchestrator/resources');
  final Future<Map<Object?, Object?>?> Function() _sampler;
  final void Function(String) _logger;
  final Queue<ResourceSample> _history = Queue<ResourceSample>();
  List<ResourceSample> get history => List.unmodifiable(_history);
  ResourceSample? latest;
  Map<String, int> native = const {};
  Map<String, int> Function()? readNative;
  String phase = 'idle';
  // Shared by chat/provider instances, bounded, and local to this process.
  // A healthy post-release sample must not erase pressure learned under load.
  final Set<String> _memoryConstrainedModels = <String>{};
  bool isMemoryConstrained(String model) =>
      _memoryConstrainedModels.contains(model);
  void recordModelPressure(String model) {
    if (model.isEmpty || _disposed) return;
    if (_memoryConstrainedModels.length >= 16 &&
        !_memoryConstrainedModels.contains(model)) {
      _memoryConstrainedModels.remove(_memoryConstrainedModels.first);
    }
    _memoryConstrainedModels.add(model);
  }
  Timer? _timer;
  Future<ResourceSample?>? _pending;
  Future<Map<Object?, Object?>?>? _sensorPending;
  int _owners = 0;
  bool _disposed = false;
  final Set<VoidCallback> _criticalListeners = {};
  void addCriticalListener(VoidCallback listener) =>
      _criticalListeners.add(listener);
  void removeCriticalListener(VoidCallback listener) =>
      _criticalListeners.remove(listener);

  static Future<Map<Object?, Object?>?> _platformSample() async {
    if (kIsWeb ||
        (defaultTargetPlatform != TargetPlatform.android &&
            defaultTargetPlatform != TargetPlatform.windows)) {
      return null;
    }
    return _channel.invokeMapMethod<Object?, Object?>('sample');
  }

  void retain() {
    if (_disposed) return;
    _owners++;
    _timer ??= Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(sample());
    });
    unawaited(sample());
  }

  void release() {
    if (_owners > 0) _owners--;
    if (_owners == 0) {
      _timer?.cancel();
      _timer = null;
    }
  }

  Future<ResourceSample?> sample() => _disposed
      ? Future.value(null)
      : _pending ??= _takeSample().whenComplete(() {
          _pending = null;
        });

  /// Waits for Android memory pressure to become genuinely non-critical.
  ///
  /// A running-critical trim callback is intentionally respected, but Android
  /// telemetry keeps the most recent trim level for a short bounded window.
  /// Callers that retry immediately after unloading a model can therefore see
  /// a stale critical signal even when free RAM has already recovered.
  ///
  /// This helper never treats an unavailable sample as healthy and remains
  /// bounded/cancellable so runtime gates still fail closed.
  Future<bool> waitForNonCritical({
    Duration timeout = const Duration(seconds: 12),
    Duration pollInterval = const Duration(seconds: 1),
    bool Function()? isCancelled,
  }) async {
    final deadline = DateTime.now().add(timeout);
    while (!_disposed) {
      if (isCancelled?.call() == true) {
        return false;
      }

      final reading = await sample();
      if (reading != null && !reading.critical) {
        return true;
      }

      final remaining = deadline.difference(DateTime.now());
      if (remaining <= Duration.zero) {
        return false;
      }

      final delay = remaining < pollInterval ? remaining : pollInterval;
      if (delay > Duration.zero) {
        await Future<void>.delayed(delay);
      }
    }
    return false;
  }
  Future<ResourceSample?> _takeSample() async {
    ResourceSample? reading;
    try {
      final pending = _sensorPending ??=
          Future<Map<Object?, Object?>?>.sync(_sampler).whenComplete(() {
        _sensorPending = null;
      });
      final data = await pending.timeout(const Duration(seconds: 1));
      if (data != null) reading = ResourceSample(data);
    } on Object {
      /* Missing plugin/unsupported platform is not zero RAM. */
    }
    if (_disposed) return null;
    latest = reading;
    try {
      native = Map<String, int>.of(readNative?.call() ?? const {})
        ..removeWhere((key, value) => value < 0);
    } on Object {
      native = const {};
    }
    if (reading != null) {
      if (_history.length >= 60) _history.removeFirst();
      _history.addLast(reading);
      try {
        _logger(
          '[RESOURCE_SAMPLE] available_bytes=${reading.availableBytes ?? -1} '
          'rss_bytes=${reading.rssBytes ?? -1} native_heap_bytes=${reading.nativeHeapBytes ?? -1} '
          'battery_temp_decic=${reading.batteryTemperatureDeciC ?? -1} '
          'critical=${reading.critical} phase=$phase '
          'gpu_layers=${native['gpu_layers'] ?? -1} '
          'decode_calls=${native['decode_calls'] ?? -1} '
          'prefill_ms=${native['prefill_ms'] ?? -1} '
          'total_bytes=${reading.totalBytes ?? -1} threshold_bytes=${reading.thresholdBytes ?? -1} '
          'pressure=${reading.pressure} low_memory=${reading.lowMemory} trim_level=${reading.trimLevel} '
          'n_ctx=${native['context'] ?? -1} n_batch=${native['batch'] ?? -1} '
          'n_ubatch=${native['micro_batch'] ?? -1}',
        );
      } on Object {
        // Diagnostics must never disable the memory guard or sampling.
      }
      if (reading.critical) {
        for (final listener in List<VoidCallback>.of(_criticalListeners)) {
          try {
            listener();
          } on Object {
            // Notify every owner even if another cancellation handler fails.
          }
        }
      }
    }
    notifyListeners();
    return reading;
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _criticalListeners.clear();
    readNative = null;
    super.dispose();
  }
}
