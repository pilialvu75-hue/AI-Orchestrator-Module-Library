import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/linux_update_installer.dart';

void main() {
  late Directory tempDirectory;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'ai-orchestrator-linux-update-test-',
    );
  });

  tearDown(() async {
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('accepts a Debian package only when size and SHA-256 match', () async {
    final bytes = List<int>.generate(4096, (index) => index % 251);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.deb');
    await file.writeAsBytes(bytes, flush: true);
    final expectedSha = sha256.convert(bytes).toString();
    final installer = LinuxUpdateInstaller(
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

  test('rejects a same-sized package when one byte changes', () async {
    final original = List<int>.generate(4096, (index) => index % 251);
    final tampered = List<int>.from(original)..[2048] ^= 0xff;
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.deb');
    await file.writeAsBytes(tampered, flush: true);
    final expectedSha = sha256.convert(original).toString();
    final installer = LinuxUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: tampered.length,
      expectedSha256: expectedSha,
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('SHA-256'));
  });

  test('rejects non-Debian extension before launch', () async {
    final bytes = List<int>.filled(128, 7);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}update.tar.gz');
    await file.writeAsBytes(bytes, flush: true);
    final installer = LinuxUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: bytes.length,
      expectedSha256: sha256.convert(bytes).toString(),
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('.deb'));
  });

  test('launch uses injected desktop opener', () async {
    String? launchedPath;
    final installer = LinuxUpdateInstaller(
      launcher: (path) async {
        launchedPath = path;
        return true;
      },
    );
    final path = '${tempDirectory.path}${Platform.pathSeparator}update.deb';

    final launched = await installer.launch(path);

    expect(launched, isTrue);
    expect(launchedPath, path);
  });
}
