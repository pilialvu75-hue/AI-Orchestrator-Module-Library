import 'package:flutter/foundation.dart';
import '../core/runtime/inference/resource_monitor.dart';

/// Visible-panel resource sampling. Reuses the original monitor's single
/// in-flight request and bounded history. No device identifiers are persisted.
class ResourceDiagnostics extends ChangeNotifier {
  ResourceDiagnostics({Future<Map<Object?, Object?>?> Function()? sampler})
      : _monitor = ResourceMonitor(sampler: sampler, logger: (_) {}) {
    _monitor.addListener(notifyListeners);
  }
  final ResourceMonitor _monitor;
  bool _active = false;
  ResourceSample? get latest => _monitor.latest;
  List<ResourceSample> get history => _monitor.history;
  Future<ResourceSample?> sample() => _monitor.sample();

  void startVisibleSampling() {
    if (_active) return;
    _active = true;
    _monitor.retain();
  }

  void stopVisibleSampling() {
    if (!_active) return;
    _active = false;
    _monitor.release();
  }

  @override
  void dispose() {
    stopVisibleSampling();
    _monitor.removeListener(notifyListeners);
    _monitor.dispose();
    super.dispose();
  }
}
