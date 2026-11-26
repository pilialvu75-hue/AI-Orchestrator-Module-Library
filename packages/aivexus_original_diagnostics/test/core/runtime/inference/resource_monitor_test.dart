import 'dart:async';

import 'package:aivexus_original_diagnostics/core/runtime/inference/android/native_generation_budget.dart';
import 'package:aivexus_original_diagnostics/core/runtime/inference/resource_monitor.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('system CPU accepts measured zero and rejects unavailable or invalid data', () {
    for (final value in [0, 37.5, 100]) {
      expect(ResourceSample({'systemCpuPercent': value}).systemCpuPercent,
          value.toDouble());
    }
    for (final value in [null, -1, 101, double.nan, double.infinity, '25']) {
      expect(ResourceSample({'systemCpuPercent': value}).systemCpuPercent,
          isNull);
    }
    expect(ResourceSample({}).systemCpuPercent, isNull);
    expect(ResourceSample({'rssBytes': 123456}).rssBytes, 123456);
  });

  test('Windows resource channel returns real RAM fields without inventing Android data',
      () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    const channel = MethodChannel('com.aiorchestrator/resources');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final monitor = ResourceMonitor(logger: (_) {});
    addTearDown(() {
      monitor.dispose();
      messenger.setMockMethodCallHandler(channel, null);
      debugDefaultTargetPlatformOverride = null;
    });
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'sample');
      return {'availableBytes': 4 << 30, 'totalBytes': 16 << 30};
    });
    final sample = await monitor.sample();
    expect(sample?.availableBytes, 4 << 30);
    expect(sample?.totalBytes, 16 << 30);
    expect(sample?.thresholdBytes, isNull);
    expect(sample?.pressure, 'unknown');
    expect(sample?.critical, isFalse);
  });
  test('Phi remembers pressure after unloading and uses a smaller next session',
      () async {
    var data = <Object?, Object?>{
      'availableBytes': 892604416,
      'thresholdBytes': 408944640,
      'totalBytes': 7575265280,
    };
    final monitor = ResourceMonitor(
      sampler: () async => data,
      logger: (_) {},
    );

    final underLoad = await monitor.sample();
    expect(underLoad!.pressured, isTrue);
    monitor.recordModelPressure('phi3_5_mini');

    data = <Object?, Object?>{
      'availableBytes': 3970293760,
      'thresholdBytes': 408944640,
      'totalBytes': 7575265280,
    };
    final recovered = await monitor.sample();
    expect(recovered!.pressured, isFalse);

    final profile = ResourceProfile.select(
      recovered,
      phi: true,
      requestedGpuLayers: 50,
      memoryConstrained: monitor.isMemoryConstrained('phi3_5_mini'),
    );
    expect(
      <int>[profile.context, profile.batch, profile.microBatch],
      <int>[1536, 64, 16],
    );
    expect(profile.reason, 'phi_memory_recovery');
    expect(
      NativeGenerationBudget.generationReserve(
        context: profile.context,
        promptTokens: 1188,
        requested: 1024,
        safetyMargin: 32,
      ),
      316,
    );
    expect(monitor.isMemoryConstrained('nemotron3_nano_4b'), isFalse);

    var cancelled = false;
    monitor.addCriticalListener(() => cancelled = true);
    data = <Object?, Object?>{
      'availableBytes': 922714112,
      'thresholdBytes': 408944640,
      'trimLevel': 15,
    };
    expect((await monitor.sample())!.critical, isTrue);
    expect(cancelled, isTrue);

    monitor.dispose();
  });

  test('learned profiles do not change unrelated models or CPU defaults', () {
    expect(
      ResourceProfile.select(
        null,
        phi: false,
        memoryConstrained: true,
      ).context,
      4096,
    );
    expect(ResourceProfile.select(null, phi: true).context, 2048);
  });

  test('8 GiB phones use a smaller non-Phi allocation before pressure', () {
    final sample = ResourceSample({
      'totalBytes': 7575265280, 'availableBytes': 2255867904,
      'thresholdBytes': 408944640,
    });
    expect(sample.pressured, isFalse);
    final profile = ResourceProfile.select(sample, phi: false);
    expect(profile.context, 2048);
    expect(profile.batch, 128);
    expect(profile.microBatch, 32);
    expect(profile.reason, 'device_memory_conservative');
    expect(ResourceProfile.select(ResourceSample({'totalBytes': 12 << 30}),
        phi: false).context, 4096);
  });
  test('aggressive non-Phi GPU offload starts pressure-compatible', () {
    final sample = ResourceSample({
      'totalBytes': 7575265280,
      'availableBytes': 2255867904,
      'thresholdBytes': 408944640,
    });
    final profile = ResourceProfile.select(
      sample,
      phi: false,
      requestedGpuLayers: 50,
    );
    expect(profile.context, 2048);
    expect(profile.batch, 128);
    expect(profile.microBatch, 32);
    expect(profile.reason, 'device_gpu_conservative');
  });

  test('aggressive Phi GPU offload starts pressure-compatible', () {
    final sample = ResourceSample({
      'totalBytes': 7575265280,
      'availableBytes': 2255867904,
      'thresholdBytes': 408944640,
    });
    final conservative = ResourceProfile.select(
      sample,
      phi: true,
      requestedGpuLayers: 10,
    );
    expect(conservative.microBatch, 64);
    expect(conservative.reason, 'phi_conservative');

    final aggressive = ResourceProfile.select(
      sample,
      phi: true,
      requestedGpuLayers: 50,
    );
    expect(aggressive.context, 2048);
    expect(aggressive.batch, 128);
    expect(aggressive.microBatch, 32);
    expect(aggressive.reason, 'phi_gpu_conservative');
  });

  test('logging and listener errors cannot prevent remaining RAM guards',
      () async {
    var guarded = false;
    final monitor = ResourceMonitor(
      sampler: () async => {'lowMemory': true},
      logger: (_) => throw StateError('log storage unavailable'),
    );
    monitor.addCriticalListener(() => throw StateError('failed handler'));
    monitor.addCriticalListener(() => guarded = true);
    final sample = await monitor.sample();
    expect(sample?.critical, isTrue);
    expect(guarded, isTrue);
    monitor.dispose();
  });
  test('battery temperature is exposed only as the Android thermal proxy', () {
    final sample = ResourceSample(<Object?, Object?>{
      'batteryTempDeciC': 367,
    });
    expect(sample.batteryTemperatureDeciC, 367);
    expect(sample.batteryTemperatureC, 36.7);
    expect(
      ResourceSample(<Object?, Object?>{'batteryTempDeciC': -1})
          .batteryTemperatureC,
      isNull,
    );
  });

  test('benchmark hardware profile uses only device class metadata', () {
    final sample = ResourceSample(<Object?, Object?>{
      'deviceManufacturer': 'samsung',
      'deviceModel': 'SM-S721B',
      'deviceName': 'r12s',
      'sdkInt': 36,
      'primaryAbi': 'arm64-v8a',
      'totalBytes': 7575265280,
    });

    expect(
      sample.benchmarkHardwareProfile,
      'android|manufacturer:samsung|model:SM-S721B|device:r12s|'
      'sdk:36|abi:arm64-v8a|ram:7575265280',
    );
  });

  test('partial and non-finite samples do not claim normal memory', () {
    expect(ResourceSample({}).pressure, 'unknown');
    expect(ResourceSample({'availableBytes': double.infinity}).availableBytes,
        isNull);
    expect(
        ResourceSample({'availableBytes': 2 << 30, 'thresholdBytes': 100})
            .pressure,
        'normal');
    expect(ResourceSample({'lowMemory': true}).pressure, 'critical');
  });
  test('disposed monitor cannot restart platform polling', () async {
    var calls = 0;
    final monitor = ResourceMonitor(
        sampler: () async {
          calls++;
          return {};
        },
        logger: (_) {});
    monitor.dispose();
    monitor.retain();
    expect(await monitor.sample(), isNull);
    expect(calls, 0);
  });
  test('unknown memory stays unknown, UI hidden is not critical pressure', () {
    final sample = ResourceSample({'trimLevel': 20});
    expect(sample.availableBytes, isNull);
    expect(sample.critical, isFalse);
    expect(sample.pressured, isFalse);
    expect(ResourceProfile.select(null, phi: false).context, 4096);
    expect(ResourceProfile.select(null, phi: true).context, 2048);
  });
  test('system threshold and running critical signal activate the guard', () {
    for (final values in [
      {'lowMemory': true},
      {'trimLevel': 15},
      {'availableBytes': 100, 'thresholdBytes': 100},
    ]) {
      final sample = ResourceSample(values);
      expect(sample.critical, isTrue);
      final profile = ResourceProfile.select(sample, phi: false);
      expect(profile.context, 2048);
      expect(profile.microBatch, 32);
      expect(minResourceGenerationLimit(profile.context), 1024);
    }
  });
  test(
    'sampling coalesces concurrent callers and bounds the history',
    () async {
      var calls = 0;
      final gate = Completer<Map<Object?, Object?>?>();
      final monitor = ResourceMonitor(
        sampler: () {
          calls++;
          return calls == 1
              ? gate.future
              : Future.value({'availableBytes': 123});
        },
        logger: (_) {},
      );
      final first = monitor.sample();
      final second = monitor.sample();
      expect(calls, 1);
      gate.complete({'availableBytes': 456});
      expect(await first, same(await second));
      for (var i = 0; i < 70; i++) {
        await monitor.sample();
      }
      expect(monitor.history.length, 60);
      monitor.dispose();
    },
  );
  test(
    'sample failure clears stale RAM and never becomes a zero reading',
    () async {
      var fail = false;
      final monitor = ResourceMonitor(
        sampler: () async {
          if (fail) throw StateError('sensor unavailable');
          return {'lowMemory': true};
        },
        logger: (_) {},
      );
      var cancellations = 0;
      monitor.addCriticalListener(() {
        cancellations++;
      });
      await monitor.sample();
      expect(cancellations, 1);
      fail = true;
      await monitor.sample();
      expect(monitor.latest, isNull);
      expect(cancellations, 1);
      monitor.dispose();
    },
  );
  test('waitForNonCritical ignores sticky critical samples until recovery',
      () async {
    var call = 0;
    final monitor = ResourceMonitor(
      sampler: () async {
        call += 1;
        if (call < 3) {
          return <Object?, Object?>{
            'availableBytes': 3 << 30,
            'thresholdBytes': 408944640,
            'trimLevel': 15,
          };
        }
        return <Object?, Object?>{
          'availableBytes': 3 << 30,
          'thresholdBytes': 408944640,
          'trimLevel': 0,
        };
      },
      logger: (_) {},
    );

    final recovered = await monitor.waitForNonCritical(
      timeout: const Duration(milliseconds: 100),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(recovered, isTrue);
    expect(call, 3);
    monitor.dispose();
  });

  test('waitForNonCritical fails closed when pressure never recovers',
      () async {
    final monitor = ResourceMonitor(
      sampler: () async => <Object?, Object?>{
        'availableBytes': 3 << 30,
        'thresholdBytes': 408944640,
        'trimLevel': 15,
      },
      logger: (_) {},
    );

    final recovered = await monitor.waitForNonCritical(
      timeout: const Duration(milliseconds: 5),
      pollInterval: const Duration(milliseconds: 1),
    );

    expect(recovered, isFalse);
    monitor.dispose();
  });

  testWidgets('panel release preserves inference sampling lease', (
    tester,
  ) async {
    var calls = 0;
    final monitor = ResourceMonitor(
      sampler: () async {
        calls++;
        return {};
      },
      logger: (_) {},
    );
    monitor.retain(); // inference
    monitor.retain(); // panel
    await tester.pump();
    monitor.release();
    await tester.pump(const Duration(seconds: 2));
    expect(calls, 2);
    monitor.release();
    await tester.pump(const Duration(seconds: 4));
    expect(calls, 2);
    monitor.dispose();
  });
}
