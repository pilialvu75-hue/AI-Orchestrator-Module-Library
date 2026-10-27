import 'dart:io';

import 'package:ai_orchestrator/core/orchestrator/state_engine/chat_attachment.dart';
import 'package:ai_orchestrator/features/chat/data/services/chat_local_image_vision_service.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.aiorchestrator/local_image_vision');
  late Directory dir;
  late File file;
  late ChatAttachment attachment;
  var calls = 0;
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() async {
    calls = 0;
    dir = await Directory.systemTemp.createTemp('local-vision-test-');
    file = File('${dir.path}/image.png');
    await file.writeAsBytes(<int>[137, 80, 78, 71, 13, 10, 26, 10, 0, 0]);
    attachment = ChatAttachment(
      id: 'img-local',
      type: ChatAttachmentType.image,
      path: file.path,
      name: 'image.png',
      mimeType: 'image/png',
    );
  });

  tearDown(() async {
    messenger.setMockMethodCallHandler(channel, null);
    await dir.delete(recursive: true);
  });

  test('LOCAL obtains offline labels without sending prompt to native bridge',
      () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      expect(call.method, 'labelImage');
      final arguments = call.arguments as Map<Object?, Object?>;
      expect(arguments.keys, <String>['path']);
      expect(arguments['path'], file.path);
      return <Map<String, Object>>[
        <String, Object>{'label': 'Apple', 'confidence': 0.92},
        <String, Object>{'label': 'Fruit', 'confidence': 0.74},
        <String, Object>{'label': 'Guess', 'confidence': 0.15},
      ];
    });
    final service = AndroidChatLocalImageVisionService(
      channel: channel,
      supportedPlatform: true,
    );
    final response = await service.analyze(
      providerId: 'local',
      image: attachment,
      prompt: 'Dammi i colori precisi',
    );
    expect(response.providerId, 'localImageLabels');
    expect(response.text, contains('Apple (92%)'));
    expect(response.text, contains('Fruit (74%)'));
    expect(response.text, isNot(contains('Guess')));
    expect(response.text, contains('Non posso ancora dedurre'));
    expect(response.text, contains('Nessuna immagine è stata inviata al Cloud'));
    expect(calls, 1);
  });

  test('no labels yields an honest limited result', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    final response = await AndroidChatLocalImageVisionService(
      channel: channel, supportedPlatform: true,
    ).analyze(providerId: 'local', image: attachment, prompt: '');
    expect(response.text, contains('Non ho riconosciuto categorie'));
    expect(calls, 1);
  });

  test('desktop without backend fails without forwarding the photo', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    await expectLater(
      AndroidChatLocalImageVisionService(
        channel: channel, supportedPlatform: false,
      ).analyze(providerId: 'local', image: attachment, prompt: ''),
      throwsUnsupportedError,
    );
    expect(calls, 0);
  });

  test('invalid and oversized local photos never enter native bridge',
      () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    final service = AndroidChatLocalImageVisionService(
      channel: channel, supportedPlatform: true,
    );
    await file.delete();
    await expectLater(
      service.analyze(providerId: 'local', image: attachment, prompt: ''),
      throwsStateError,
    );
    await file.writeAsBytes(List<int>.filled(
      AndroidChatLocalImageVisionService.maxImageBytes + 1, 0,
    ));
    await expectLater(
      service.analyze(providerId: 'local', image: attachment, prompt: ''),
      throwsStateError,
    );
    expect(calls, 0);
  });

  test('Cloud provider cannot be sent through local analyzer', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return <Object>[];
    });
    await expectLater(
      AndroidChatLocalImageVisionService(
        channel: channel, supportedPlatform: true,
      ).analyze(providerId: 'gemini', image: attachment, prompt: ''),
      throwsStateError,
    );
    expect(calls, 0);
  });

  test('native classifier error is reported instead of fake vision output',
      () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      throw PlatformException(code: 'LOCAL_VISION_FAILED',
          message: 'Riconoscimento visivo locale non riuscito.');
    });
    await expectLater(
      AndroidChatLocalImageVisionService(
        channel: channel, supportedPlatform: true,
      ).analyze(providerId: 'local', image: attachment, prompt: ''),
      throwsA(isA<PlatformException>()),
    );
  });
}
