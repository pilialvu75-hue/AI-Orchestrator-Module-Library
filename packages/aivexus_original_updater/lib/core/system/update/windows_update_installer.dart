import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';

class WindowsInstallerVerification {
  const WindowsInstallerVerification({
    required this.valid,
    required this.exists,
    required this.sizeBytes,
    required this.sha256,
    required this.reason,
  });

  final bool valid;
  final bool exists;
  final int sizeBytes;
  final String? sha256;
  final String reason;
}

abstract interface class WindowsUpdateInstallerPort {
  Future<String> download({
    required String url,
    required String fileName,
    required String finalPath,
    required String partialPath,
    required int expectedSizeBytes,
    required String expectedSha256,
    required void Function(int received, int total) onProgress,
  });

  Future<WindowsInstallerVerification> verify({
    required String filePath,
    required int expectedSizeBytes,
    required String expectedSha256,
  });

  Future<bool> launch(String filePath);
}

class WindowsUpdateInstaller implements WindowsUpdateInstallerPort {
  WindowsUpdateInstaller({
    Dio? dio,
    Future<bool> Function(String filePath)? launcher,
  })  : _dio = dio ?? Dio(),
        _launcher = launcher;

  final Dio _dio;
  final Future<bool> Function(String filePath)? _launcher;

  static const Duration _downloadTimeout = Duration(minutes: 15);

  @override
  Future<String> download({
    required String url,
    required String fileName,
    required String finalPath,
    required String partialPath,
    required int expectedSizeBytes,
    required String expectedSha256,
    required void Function(int received, int total) onProgress,
  }) async {
    _validateArtifactMetadata(
      url: url,
      fileName: fileName,
      expectedSizeBytes: expectedSizeBytes,
      expectedSha256: expectedSha256,
    );

    final finalFile = File(finalPath);
    if (await finalFile.exists()) {
      final existing = await verify(
        filePath: finalPath,
        expectedSizeBytes: expectedSizeBytes,
        expectedSha256: expectedSha256,
      );
      if (existing.valid) {
        onProgress(existing.sizeBytes, expectedSizeBytes);
        return finalPath;
      }
      await finalFile.delete();
    }

    final partialFile = File(partialPath);
    await partialFile.parent.create(recursive: true);

    var existingPartialBytes =
        await partialFile.exists() ? await partialFile.length() : 0;
    if (existingPartialBytes >= expectedSizeBytes) {
      // A partial file at or beyond the advertised final size is not safe to
      // append to. A complete valid installer would already have been moved to
      // [finalPath], so restart this download from byte zero.
      await partialFile.delete();
      existingPartialBytes = 0;
    }

    var response = await _requestDownload(
      url: url,
      rangeStart: existingPartialBytes > 0 ? existingPartialBytes : null,
    );

    var supportsResume = false;
    if (existingPartialBytes > 0 &&
        response.statusCode == HttpStatus.partialContent) {
      supportsResume = _isValidResumeResponse(
        response: response,
        requestedStart: existingPartialBytes,
        expectedSizeBytes: expectedSizeBytes,
      );

      if (!supportsResume) {
        // Never append a 206 response unless Content-Range proves that it
        // starts exactly where our local .part file ends and targets the same
        // artifact size. Some proxies/CDNs can return stale or malformed range
        // responses; silently appending those bytes would corrupt the file.
        await _discardResponseBody(response);
        if (await partialFile.exists()) {
          await partialFile.delete();
        }
        existingPartialBytes = 0;
        response = await _requestDownload(url: url);
      }
    } else if (existingPartialBytes > 0 &&
        response.statusCode == HttpStatus.ok) {
      // Server ignored Range. This is safe as long as we overwrite the .part
      // file instead of appending to it.
      existingPartialBytes = 0;
    }

    if (!supportsResume &&
        response.statusCode == HttpStatus.partialContent &&
        !_isValidFullRangeResponse(
          response: response,
          expectedSizeBytes: expectedSizeBytes,
        )) {
      await _discardResponseBody(response);
      throw StateError(
        'Windows installer server returned an invalid Content-Range for a '
        'full download.',
      );
    }

    final sink = partialFile.openWrite(
      mode: supportsResume ? FileMode.append : FileMode.write,
    );
    var receivedBytes = supportsResume ? existingPartialBytes : 0;

    try {
      final stream = response.data?.stream;
      if (stream == null) {
        throw StateError('Windows installer response body is empty.');
      }
      await for (final chunk in stream) {
        sink.add(chunk);
        receivedBytes += chunk.length;
        if (receivedBytes > expectedSizeBytes) {
          throw StateError(
            'Windows installer exceeded advertised size: '
            'expected=$expectedSizeBytes received=$receivedBytes',
          );
        }
        onProgress(receivedBytes, expectedSizeBytes);
      }
    } finally {
      await sink.flush();
      await sink.close();
    }

    if (receivedBytes != expectedSizeBytes) {
      throw StateError(
        'Windows installer download ended at an unexpected size: '
        'expected=$expectedSizeBytes received=$receivedBytes',
      );
    }

    if (await finalFile.exists()) {
      await finalFile.delete();
    }
    await partialFile.rename(finalPath);

    final verification = await verify(
      filePath: finalPath,
      expectedSizeBytes: expectedSizeBytes,
      expectedSha256: expectedSha256,
    );
    if (!verification.valid) {
      if (await finalFile.exists()) {
        await finalFile.delete();
      }
      throw StateError(
        'Downloaded Windows installer failed verification: '
        '${verification.reason}',
      );
    }
    onProgress(verification.sizeBytes, expectedSizeBytes);
    return finalPath;
  }

  Future<Response<ResponseBody>> _requestDownload({
    required String url,
    int? rangeStart,
  }) {
    final headers = <String, dynamic>{};
    if (rangeStart != null && rangeStart > 0) {
      headers[HttpHeaders.rangeHeader] = 'bytes=$rangeStart-';
    }
    return _dio.get<ResponseBody>(
      url,
      options: Options(
        responseType: ResponseType.stream,
        followRedirects: true,
        receiveTimeout: _downloadTimeout,
        headers: headers,
        validateStatus: (status) =>
            status != null &&
            (status == HttpStatus.ok || status == HttpStatus.partialContent),
      ),
    );
  }

  bool _isValidResumeResponse({
    required Response<ResponseBody> response,
    required int requestedStart,
    required int expectedSizeBytes,
  }) {
    if (response.statusCode != HttpStatus.partialContent) return false;
    final range = _parseContentRange(
      response.headers.value(HttpHeaders.contentRangeHeader),
    );
    if (range == null ||
        range.start != requestedStart ||
        range.end != expectedSizeBytes - 1 ||
        range.total != expectedSizeBytes) {
      return false;
    }

    final contentLength = int.tryParse(
      response.headers.value(Headers.contentLengthHeader) ?? '',
    );
    return contentLength == null || contentLength == range.length;
  }

  bool _isValidFullRangeResponse({
    required Response<ResponseBody> response,
    required int expectedSizeBytes,
  }) {
    if (response.statusCode != HttpStatus.partialContent) return true;
    final range = _parseContentRange(
      response.headers.value(HttpHeaders.contentRangeHeader),
    );
    if (range == null ||
        range.start != 0 ||
        range.end != expectedSizeBytes - 1 ||
        range.total != expectedSizeBytes) {
      return false;
    }
    final contentLength = int.tryParse(
      response.headers.value(Headers.contentLengthHeader) ?? '',
    );
    return contentLength == null || contentLength == range.length;
  }

  _ContentRange? _parseContentRange(String? raw) {
    if (raw == null) return null;
    final match = RegExp(r'^bytes\s+(\d+)-(\d+)/(\d+)$')
        .firstMatch(raw.trim().toLowerCase());
    if (match == null) return null;
    final start = int.tryParse(match.group(1)!);
    final end = int.tryParse(match.group(2)!);
    final total = int.tryParse(match.group(3)!);
    if (start == null ||
        end == null ||
        total == null ||
        start < 0 ||
        end < start ||
        total <= end) {
      return null;
    }
    return _ContentRange(start: start, end: end, total: total);
  }

  Future<void> _discardResponseBody(Response<ResponseBody> response) async {
    final stream = response.data?.stream;
    if (stream == null) return;
    final subscription = stream.listen((_) {});
    await subscription.cancel();
  }

  @override
  Future<WindowsInstallerVerification> verify({
    required String filePath,
    required int expectedSizeBytes,
    required String expectedSha256,
  }) async {
    final file = File(filePath);
    if (!filePath.toLowerCase().endsWith('.exe')) {
      return const WindowsInstallerVerification(
        valid: false,
        exists: false,
        sizeBytes: 0,
        sha256: null,
        reason: 'installer path is not an .exe file',
      );
    }
    if (!await file.exists()) {
      return const WindowsInstallerVerification(
        valid: false,
        exists: false,
        sizeBytes: 0,
        sha256: null,
        reason: 'installer file does not exist',
      );
    }

    final sizeBytes = await file.length();
    if (sizeBytes != expectedSizeBytes) {
      return WindowsInstallerVerification(
        valid: false,
        exists: true,
        sizeBytes: sizeBytes,
        sha256: null,
        reason:
            'installer size mismatch: expected=$expectedSizeBytes actual=$sizeBytes',
      );
    }

    final digest = await sha256.bind(file.openRead()).first;
    final actualSha256 = digest.toString().toLowerCase();
    final normalizedExpected = expectedSha256.trim().toLowerCase();
    if (actualSha256 != normalizedExpected) {
      return WindowsInstallerVerification(
        valid: false,
        exists: true,
        sizeBytes: sizeBytes,
        sha256: actualSha256,
        reason: 'installer SHA-256 mismatch',
      );
    }

    return WindowsInstallerVerification(
      valid: true,
      exists: true,
      sizeBytes: sizeBytes,
      sha256: actualSha256,
      reason: 'ok',
    );
  }

  @override
  Future<bool> launch(String filePath) async {
    if (_launcher != null) {
      return _launcher(filePath);
    }
    if (!Platform.isWindows) {
      return false;
    }
    final file = File(filePath);
    if (!await file.exists() || !filePath.toLowerCase().endsWith('.exe')) {
      return false;
    }
    final process = await Process.start(
      filePath,
      const <String>[],
      mode: ProcessStartMode.detached,
    );
    return process.pid > 0;
  }

  void _validateArtifactMetadata({
    required String url,
    required String fileName,
    required int expectedSizeBytes,
    required String expectedSha256,
  }) {
    final uri = Uri.tryParse(url);
    if (uri == null ||
        !(uri.scheme == 'https' || uri.scheme == 'http') ||
        uri.host.isEmpty) {
      throw ArgumentError.value(url, 'url', 'Must be a valid HTTP(S) URL');
    }
    if (fileName.isEmpty ||
        fileName.contains('/') ||
        fileName.contains('\\') ||
        !fileName.toLowerCase().endsWith('.exe')) {
      throw ArgumentError.value(
        fileName,
        'fileName',
        'Must be a safe .exe filename',
      );
    }
    if (expectedSizeBytes <= 0) {
      throw ArgumentError.value(
        expectedSizeBytes,
        'expectedSizeBytes',
        'Must be greater than zero',
      );
    }
    if (!RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(expectedSha256.trim())) {
      throw ArgumentError.value(
        expectedSha256,
        'expectedSha256',
        'Must be a 64-character hexadecimal SHA-256',
      );
    }
  }
}

class _ContentRange {
  const _ContentRange({
    required this.start,
    required this.end,
    required this.total,
  });

  final int start;
  final int end;
  final int total;

  int get length => end - start + 1;
}
