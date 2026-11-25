import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/windows_update_installer.dart';

class _DownloadResponse {
  const _DownloadResponse({
    required this.bytes,
    required this.statusCode,
    this.headers = const <String, List<String>>{},
  });

  final List<int> bytes;
  final int statusCode;
  final Map<String, List<String>> headers;
}

class _SequenceDownloadAdapter implements HttpClientAdapter {
  _SequenceDownloadAdapter(this.responses);

  final List<_DownloadResponse> responses;
  final List<String?> ranges = <String?>[];
  var calls = 0;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    ranges.add(options.headers[HttpHeaders.rangeHeader]?.toString());
    if (calls >= responses.length) {
      throw StateError('No synthetic response left for call ${calls + 1}.');
    }
    final response = responses[calls++];
    return ResponseBody.fromBytes(
      response.bytes,
      response.statusCode,
      headers: response.headers,
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late Directory tempDirectory;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'ai-orchestrator-windows-update-test-',
    );
  });

  tearDown(() async {
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  test('accepts an installer only when size and SHA-256 match', () async {
    final bytes = List<int>.generate(4096, (index) => index % 251);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}setup.exe');
    await file.writeAsBytes(bytes, flush: true);
    final expectedSha = sha256.convert(bytes).toString();
    final installer = WindowsUpdateInstaller(
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

  test('rejects a same-sized installer when one byte changes', () async {
    final original = List<int>.generate(4096, (index) => index % 251);
    final tampered = List<int>.from(original)..[2048] ^= 0xff;
    final file = File('${tempDirectory.path}${Platform.pathSeparator}setup.exe');
    await file.writeAsBytes(tampered, flush: true);
    final expectedSha = sha256.convert(original).toString();
    final installer = WindowsUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: tampered.length,
      expectedSha256: expectedSha,
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('SHA-256'));
  });

  test('rejects wrong extension before launch', () async {
    final bytes = List<int>.filled(128, 7);
    final file = File('${tempDirectory.path}${Platform.pathSeparator}setup.zip');
    await file.writeAsBytes(bytes, flush: true);
    final installer = WindowsUpdateInstaller();

    final result = await installer.verify(
      filePath: file.path,
      expectedSizeBytes: bytes.length,
      expectedSha256: sha256.convert(bytes).toString(),
    );

    expect(result.valid, isFalse);
    expect(result.reason, contains('.exe'));
  });

  test('launch uses injected launcher only after caller verification', () async {
    String? launchedPath;
    final installer = WindowsUpdateInstaller(
      launcher: (path) async {
        launchedPath = path;
        return true;
      },
    );
    final path = '${tempDirectory.path}${Platform.pathSeparator}setup.exe';

    final launched = await installer.launch(path);

    expect(launched, isTrue);
    expect(launchedPath, path);
  });

  test('resume appends only when Content-Range matches local offset', () async {
    final complete = List<int>.generate(8, (index) => index + 1);
    final partial = complete.sublist(0, 4);
    final remainder = complete.sublist(4);
    final finalPath =
        '${tempDirectory.path}${Platform.pathSeparator}AI-Orchestrator-Setup-x64.exe';
    final partialPath = '$finalPath.part';
    await File(partialPath).writeAsBytes(partial, flush: true);

    final adapter = _SequenceDownloadAdapter(<_DownloadResponse>[
      _DownloadResponse(
        bytes: remainder,
        statusCode: HttpStatus.partialContent,
        headers: const <String, List<String>>{
          HttpHeaders.contentRangeHeader: <String>['bytes 4-7/8'],
          HttpHeaders.contentLengthHeader: <String>['4'],
        },
      ),
    ]);
    final dio = Dio()..httpClientAdapter = adapter;
    final installer = WindowsUpdateInstaller(dio: dio);

    final downloaded = await installer.download(
      url: 'https://example.invalid/AI-Orchestrator-Setup-x64.exe',
      fileName: 'AI-Orchestrator-Setup-x64.exe',
      finalPath: finalPath,
      partialPath: partialPath,
      expectedSizeBytes: complete.length,
      expectedSha256: sha256.convert(complete).toString(),
      onProgress: (_, __) {},
    );

    expect(downloaded, finalPath);
    expect(adapter.calls, 1);
    expect(adapter.ranges, <String?>['bytes=4-']);
    expect(await File(finalPath).readAsBytes(), complete);
    expect(await File(partialPath).exists(), isFalse);
  });

  test('malformed resume response is discarded and restarted from byte zero',
      () async {
    final complete = List<int>.generate(8, (index) => 20 + index);
    final partial = complete.sublist(0, 4);
    final finalPath =
        '${tempDirectory.path}${Platform.pathSeparator}AI-Orchestrator-Setup-x64.exe';
    final partialPath = '$finalPath.part';
    await File(partialPath).writeAsBytes(partial, flush: true);

    final adapter = _SequenceDownloadAdapter(<_DownloadResponse>[
      const _DownloadResponse(
        bytes: <int>[99, 98, 97, 96],
        statusCode: HttpStatus.partialContent,
        headers: <String, List<String>>{
          HttpHeaders.contentRangeHeader: <String>['bytes 0-3/8'],
          HttpHeaders.contentLengthHeader: <String>['4'],
        },
      ),
      _DownloadResponse(
        bytes: complete,
        statusCode: HttpStatus.ok,
        headers: const <String, List<String>>{
          HttpHeaders.contentLengthHeader: <String>['8'],
        },
      ),
    ]);
    final dio = Dio()..httpClientAdapter = adapter;
    final installer = WindowsUpdateInstaller(dio: dio);

    final downloaded = await installer.download(
      url: 'https://example.invalid/AI-Orchestrator-Setup-x64.exe',
      fileName: 'AI-Orchestrator-Setup-x64.exe',
      finalPath: finalPath,
      partialPath: partialPath,
      expectedSizeBytes: complete.length,
      expectedSha256: sha256.convert(complete).toString(),
      onProgress: (_, __) {},
    );

    expect(downloaded, finalPath);
    expect(adapter.calls, 2);
    expect(adapter.ranges, <String?>['bytes=4-', null]);
    expect(await File(finalPath).readAsBytes(), complete);
  });

  test('download stops immediately when server exceeds advertised size',
      () async {
    final expected = List<int>.generate(8, (index) => index);
    final oversized = <int>[...expected, 99];
    final finalPath =
        '${tempDirectory.path}${Platform.pathSeparator}AI-Orchestrator-Setup-x64.exe';
    final partialPath = '$finalPath.part';

    final adapter = _SequenceDownloadAdapter(<_DownloadResponse>[
      _DownloadResponse(
        bytes: oversized,
        statusCode: HttpStatus.ok,
        headers: const <String, List<String>>{
          HttpHeaders.contentLengthHeader: <String>['9'],
        },
      ),
    ]);
    final dio = Dio()..httpClientAdapter = adapter;
    final installer = WindowsUpdateInstaller(dio: dio);

    await expectLater(
      installer.download(
        url: 'https://example.invalid/AI-Orchestrator-Setup-x64.exe',
        fileName: 'AI-Orchestrator-Setup-x64.exe',
        finalPath: finalPath,
        partialPath: partialPath,
        expectedSizeBytes: expected.length,
        expectedSha256: sha256.convert(expected).toString(),
        onProgress: (_, __) {},
      ),
      throwsA(isA<StateError>()),
    );
    expect(await File(finalPath).exists(), isFalse);
  });
}
