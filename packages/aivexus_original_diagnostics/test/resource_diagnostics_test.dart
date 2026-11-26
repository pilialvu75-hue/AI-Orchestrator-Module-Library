import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

void main() {
  test('hardware readings are measured and absent fields stay unavailable', () async {
    final monitor = ResourceDiagnostics(sampler: () async => {
      'availableBytes': 1024, 'totalBytes': 4096, 'systemCpuPercent': 0,
    });
    addTearDown(monitor.dispose);
    final sample = await monitor.sample();
    expect(sample!.availableBytes, 1024);
    expect(sample.systemCpuPercent, 0);
    expect(sample.batteryTemperatureC, isNull);
    expect(sample.nativeHeapBytes, isNull);
  });
  test('disk and process CPU preserve measured zero and reject invalid values', () {
    final sample = ResourceSample({'appVolumeFreeBytes': 0, 'appVolumeTotalBytes': 4096,
      'processCpuCorePercent': 180.5});
    expect(sample.appVolumeFreeBytes, 0);
    expect(sample.appVolumeTotalBytes, 4096);
    expect(sample.processCpuCorePercent, 180.5);
    expect(sample.systemCpuPercent, isNull);
    final invalid = ResourceSample({'appVolumeFreeBytes': -1, 'appVolumeTotalBytes': double.nan,
      'processCpuCorePercent': double.infinity});
    expect(invalid.appVolumeFreeBytes, isNull);
    expect(invalid.appVolumeTotalBytes, isNull);
    expect(invalid.processCpuCorePercent, isNull);
  });
  test('unsupported platform data remains null', () async {
    final monitor = ResourceDiagnostics(sampler: () async => null);
    addTearDown(monitor.dispose);
    expect(await monitor.sample(), isNull);
    expect(monitor.latest, isNull);
  });
}
