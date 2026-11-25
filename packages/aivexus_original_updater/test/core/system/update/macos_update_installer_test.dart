import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/macos_update_installer.dart';

void main() {
  late Directory tempDirectory;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'ai-orchestrator-macos-update-test-',
    );
  });

  tearDown(() async {
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('accepts a DMG only when size and SHA-256 match', () async {
    final bytes = List<int>.generate(4096, (index) => index % 251);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.dmg');
    await file.writeAsBytes(bytes, flush: true);
    final expectedSha = sha256.convert(bytes).toString();
    final installer = MacosUpdateInstaller(
      launcher: (_) async => true,
    );

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: bytes.length,
      expectedSha256: expectedSha,
    );

    expect(result.valid, isTrue);
    expect(result.exists, isTrue);
    expect(result.sizeBytes, bytes.length);
    expect(result.sha256, expectedSha);
  });

  test('rejects a same-sized DMG when one byte changes', () async {
    final original = List<int>.generate(4096, (index) => index % 251);
    final tampered = List<int>.from(original)..[2048] ^= 0xff;
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.dmg');
    await file.writeAsBytes(tampered, flush: true);
    final expectedSha = sha256.convert(original).toString();
    final installer = MacosUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: tampered.length,
      expectedSha256: expectedSha,
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('SHA-256'));
  });

  test('rejects a DMG when its size is not the expected release size', () async {
    final bytes = List<int>.filled(128, 7);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.dmg');
    await file.writeAsBytes(bytes, flush: true);
    final installer = MacosUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: bytes.length + 1,
      expectedSha256: sha256.convert(bytes).toString(),
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('size mismatch'));
  });

  test('rejects wrong extension before launch', () async {
    final bytes = List<int>.filled(128, 7);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.zip');
    await file.writeAsBytes(bytes, flush: true);
    final installer = MacosUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: bytes.length,
      expectedSha256: sha256.convert(bytes).toString(),
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('.dmg'));
    expect(await installer.launch(file.path), isFalse);
  });

  test('launch uses injected launcher only for an existing DMG', () async {
    String? launchedPath;
    final installer = MacosUpdateInstaller(
      launcher: (path) async {
        launchedPath = path;
        return true;
      },
    );
    final path = '${tempDirectory.path}${Platform.pathSeparator}update.dmg';
    await File(path).writeAsBytes(const <int>[1, 2, 3], flush: true);

    final launched = await installer.launch(path);

    expect(launched, isTrue);
    expect(launchedPath, path);
    expect(
      await installer.launch(
        '${tempDirectory.path}${Platform.pathSeparator}missing.dmg',
      ),
      isFalse,
    );
  });

  test('download metadata rejects non-HTTPS sources before network access', () async {
    final installer = MacosUpdateInstaller();
    final finalPath =
        '${tempDirectory.path}${Platform.pathSeparator}AI-Orchestrator-macOS.dmg';
    final expectedSha = List<String>.filled(64, 'a').join();

    await expectLater(
      installer.download(
        url: 'http://example.invalid/AI-Orchestrator-macOS.dmg',
        fileName: 'AI-Orchestrator-macOS.dmg',
        finalPath: finalPath,
        partialPath: '$finalPath.part',
        expectedSizeBytes: 1024,
        expectedSha256: expectedSha,
        onProgress: (_, __) {},
      ),
      throwsArgumentError,
    );
  });

  test('download metadata rejects unsafe DMG filenames', () async {
    final installer = MacosUpdateInstaller();
    final finalPath =
        '${tempDirectory.path}${Platform.pathSeparator}AI-Orchestrator-macOS.dmg';
    final expectedSha = List<String>.filled(64, 'b').join();

    await expectLater(
      installer.download(
        url: 'https://example.invalid/AI-Orchestrator-macOS.dmg',
        fileName: '../AI-Orchestrator-macOS.dmg',
        finalPath: finalPath,
        partialPath: '$finalPath.part',
        expectedSizeBytes: 1024,
        expectedSha256: expectedSha,
        onProgress: (_, __) {},
      ),
      throwsArgumentError,
    );
  });
}
