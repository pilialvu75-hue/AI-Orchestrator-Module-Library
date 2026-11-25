import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart';

/// Android retains the request and completed bytes across process death.
/// Call [release] only after validation/publication, or to discard invalid data.
class BackgroundDownload {
  static const channel =
      MethodChannel('ai_orchestrator/background_downloads');

  static final Map<String, Future<void>> _active = {};

  static Future<void> transfer({
    required String url,
    required String title,
    required File destination,
    void Function(int received, int total)? onProgress,
    CancelToken? cancelToken,
  }) {
    final key = '$url\n${destination.path}';
    final running = _active[key];
    if (running != null) return running;
    final operation = _transfer(url: url, title: title, destination: destination,
        onProgress: onProgress, cancelToken: cancelToken);
    final tracked = operation.whenComplete(() { _active.remove(key); });
    _active[key] = tracked;
    return tracked;
  }

  static Future<void> _transfer({
    required String url,
    required String title,
    required File destination,
    void Function(int received, int total)? onProgress,
    CancelToken? cancelToken,
  }) async {
    void checkCancelled() {
      if (cancelToken?.isCancelled ?? false) {
        throw cancelToken!.cancelError!;
      }
    }

    checkCancelled();
    var snapshot = await channel.invokeMapMethod<String, dynamic>(
      'start', {'url': url, 'title': title},
    );
    try {
      while (true) {
        checkCancelled();
        if (snapshot == null) {
          throw StateError('Download removed. Start it again to retry.');
        }
        final received = (snapshot['received'] as num).toInt();
        final total = (snapshot['total'] as num).toInt();
        onProgress?.call(received, total);
        final status = (snapshot['status'] as num).toInt();
        if (status == 16) {
          throw StateError('Android download failed (code ${snapshot['reason']}).');
        }
        if (status == 8) {
          final source = File(snapshot['path'] as String);
          final length = await source.length();
          if (length <= 0 || (total > 0 && length != total)) {
            await release(url);
            throw StateError('Incomplete background download.');
          }
          await destination.parent.create(recursive: true);
          // Preserve an old partial until a complete replacement has been copied.
          final incoming = File('${destination.path}.incoming');
          await source.copy(incoming.path);
          checkCancelled();
          await incoming.rename(destination.path);
          return;
        }
        if (status != 1 && status != 2 && status != 4) {
          throw StateError('Unknown Android download status: $status');
        }
        await Future<void>.delayed(const Duration(milliseconds: 500));
        snapshot = await channel.invokeMapMethod<String, dynamic>(
          'status', {'url': url},
        );
      }
    } catch (_) {
      if (cancelToken?.isCancelled ?? false) {
        await channel.invokeMethod<void>('cancel', {'url': url});
      }
      rethrow;
    }
  }

  static Future<void> release(String url) =>
      channel.invokeMethod<void>('release', {'url': url});
}
