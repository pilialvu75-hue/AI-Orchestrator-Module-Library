import 'package:cantiere_local_image_vision/cantiere_local_image_vision.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.aiorchestrator/local_image_vision');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test('invokes only local filepath and filters labels without Cloud', () async {
    var calls = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      expect(call.method, 'labelImage');
      expect(call.arguments, <String, String>{'path': '/tmp/fruit.png'});
      return <Map<String, Object>>[
        {'label': 'Apple', 'confidence': 0.94},
        {'label': 'Unknown', 'confidence': 0.14}
      ];
    });
    final result = await CantiereLocalImageVision(
      supportedPlatform: true,
    ).labelFile('/tmp/fruit.png');
    expect(calls, 1);
    expect(result.labels, hasLength(1));
    expect(result.text, contains('Apple (94%)'));
    expect(result.text, isNot(contains('Unknown')));
    expect(result.text, contains('non una descrizione completa'));
  });

  test('no labels reports uncertainty, no invented details', () async {
    messenger.setMockMethodCallHandler(channel, (call) async => <Object>[]);
    final result = await CantiereLocalImageVision(
      supportedPlatform: true,
    ).labelFile('/tmp/unknown.png');
    expect(result.hasCategories, isFalse);
    expect(result.text, contains('Non ho riconosciuto categorie'));
  });

  test('unsupported target rejects before invoking native bridge', () async {
    var calls = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    await expectLater(
      CantiereLocalImageVision(
        supportedPlatform: false,
      ).labelFile('/tmp/fruit.png'),
      throwsUnsupportedError,
    );
    expect(calls, 0);
  });

  test('empty filepath rejects before invoking native bridge', () async {
    var calls = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    await expectLater(
      CantiereLocalImageVision(
        supportedPlatform: true,
      ).labelFile('  '),
      throwsArgumentError,
    );
    expect(calls, 0);
  });

  test('ML Kit errors are propagated, not replaced with fabricated labels',
      () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      throw PlatformException(code: 'LOCAL_VISION_MEMORY');
    });
    await expectLater(
      CantiereLocalImageVision(
        supportedPlatform: true,
      ).labelFile('/tmp/fruit.png'),
      throwsA(isA<PlatformException>().having(
        (e) => e.code, 'code', 'LOCAL_VISION_MEMORY',
      )),
    );
  });
}
