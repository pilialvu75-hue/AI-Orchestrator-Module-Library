import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'diagnostic_report.dart';

enum DeliveryState { idle, queued, sending, sent, retryLater, expired, rejected, unavailable }

/// One durable, explicitly approved snapshot. Retry requires a host action;
/// no background timer, automatic collection, redirect, or silent upload.
/// Endpoint configuration is supplied by the app owner, not the report.
class DiagnosticDelivery extends ChangeNotifier {
  DiagnosticDelivery({required Uri endpoint, required File queueFile,
    http.Client Function()? clientFactory, DateTime Function()? clock})
      : endpoint = _validateEndpoint(endpoint), _file = queueFile,
        _clientFactory = clientFactory ?? http.Client,
        _clock = clock ?? DateTime.now;
  final Uri endpoint;
  final File _file;
  final http.Client Function() _clientFactory;
  final DateTime Function() _clock;
  static const maxAttempts = 3;
  static const ttl = Duration(hours: 24);
  static const _delays = [Duration(minutes: 1), Duration(minutes: 5), Duration(minutes: 15)];
  DeliveryState _state = DeliveryState.idle;
  DeliveryState get state => _state;
  bool _busy = false;
  bool _disposed = false;
  bool _revoked = false;
  http.Client? _activeClient;

  static Uri _validateEndpoint(Uri uri) {
    if (uri.scheme != 'https' || uri.host.isEmpty || uri.userInfo.isNotEmpty ||
        uri.hasQuery || uri.hasFragment || uri.path.isEmpty ||
        uri.port != 443) throw ArgumentError('Explicit HTTPS endpoint required');
    return uri;
  }

  void _set(DeliveryState state) {
    _state = state;
    if (!_disposed) notifyListeners();
  }

  /// Call only after the user previews the exact report AND endpoint and
  /// explicitly approves this snapshot. No automatic upload on approval.
  Future<bool> queueApproved(DiagnosticReport report, {required bool consent}) async {
    if (!consent || _busy || _disposed || report.events.isEmpty) return false;
    _busy = true;
    try {
      final verified = DiagnosticReport.decode(report.json);
      if (await _file.exists()) return false;
      final now = _clock().toUtc();
      await _save({
        'endpoint': endpoint.toString(), 'approved': now.toIso8601String(),
        'attempts': 0, 'next': now.toIso8601String(), 'report': verified.json,
      });
      _revoked = false;
      _set(DeliveryState.queued);
      return true;
    } catch (_) {
      _set(DeliveryState.unavailable);
      return false;
    } finally { _busy = false; }
  }

  Future<void> _save(Map<String, Object> data) async {
    await _file.parent.create(recursive: true);
    final tmp = File('${_file.path}.tmp');
    try {
      await tmp.writeAsString(jsonEncode(data), flush: true);
      await tmp.rename(_file.path);
    } finally {
      if (await tmp.exists()) await tmp.delete();
    }
  }

  Future<void> _remove() async {
    if (await _file.exists()) await _file.delete();
  }

  /// Revoke pending permission. Already delivered requests cannot be recalled.
  Future<void> revoke() async {
    _revoked = true;
    _activeClient?.close();
    try { await _remove(); } catch (_) { _set(DeliveryState.unavailable); return; }
    _set(DeliveryState.idle);
  }

  Future<void> sendPending() async {
    if (_busy || _disposed || _revoked) return;
    _busy = true;
    try {
      if (!await _file.exists()) { _set(DeliveryState.idle); return; }
      if (await _file.length() > 65536) throw const FormatException('Queue too large');
      final decoded = jsonDecode(await _file.readAsString());
      if (decoded is! Map<String,dynamic> || decoded.length != 5 ||
          decoded['endpoint'] != endpoint.toString() ||
          decoded['report'] is! String || decoded['attempts'] is! int ||
          decoded['approved'] is! String || decoded['next'] is! String) {
        throw const FormatException('Invalid approval');
      }
      final report = DiagnosticReport.decode(decoded['report'] as String);
      final approved = DateTime.parse(decoded['approved'] as String).toUtc();
      final next = DateTime.parse(decoded['next'] as String).toUtc();
      final attempts = decoded['attempts'] as int;
      final now = _clock().toUtc();
      if (approved.isAfter(now) || attempts < 0 ||
          now.difference(approved) >= ttl || attempts >= maxAttempts) {
        await _remove(); _set(DeliveryState.expired); return;
      }
      if (now.isBefore(next)) { _set(DeliveryState.retryLater); return; }
      if (_revoked || _disposed) return;
      // Persist the attempt before transmission; a crash cannot reset budget.
      await _save({
        'endpoint': endpoint.toString(), 'approved': approved.toIso8601String(),
        'attempts': attempts + 1, 'next': now.add(_delays[attempts]).toIso8601String(),
        'report': report.json,
      });
      if (_revoked || _disposed) { if (_revoked) await _remove(); return; }
      _set(DeliveryState.sending);
      final client = _clientFactory();
      _activeClient = client;
      try {
        final request = http.Request('POST', endpoint)
          ..followRedirects = false
          ..headers['Content-Type'] = 'application/json'
          ..headers['Idempotency-Key'] = sha256.convert(utf8.encode('${approved.toIso8601String()}:${report.json}')).toString()
          ..body = report.json;
        final response = await client.send(request).timeout(const Duration(seconds: 10));
        final status = response.statusCode;
        if (_revoked || _disposed) return;
        if (status >= 200 && status < 300) {
          await _remove(); _set(DeliveryState.sent);
        } else if (status == 408 || status == 429 || status >= 500 && status <= 599) {
          if (attempts + 1 >= maxAttempts) { await _remove(); _set(DeliveryState.expired); }
          else { _set(DeliveryState.retryLater); }
        } else {
          await _remove(); _set(DeliveryState.rejected);
        }
      } catch (_) {
        if (!_revoked && !_disposed) {
          if (attempts + 1 >= maxAttempts) { await _remove(); _set(DeliveryState.expired); }
          else { _set(DeliveryState.retryLater); }
        }
      } finally {
        client.close();
        _activeClient = null;
      }
    } on FormatException {
      await _remove(); _set(DeliveryState.rejected);
    } catch (_) {
      _set(DeliveryState.unavailable);
    } finally {
      if (_revoked) {
        try { await _remove(); } catch (_) { _set(DeliveryState.unavailable); }
      }
      _busy = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _activeClient?.close();
    super.dispose();
  }
}
