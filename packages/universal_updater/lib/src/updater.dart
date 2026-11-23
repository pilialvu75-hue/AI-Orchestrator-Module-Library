import 'dart:convert';

import 'package:convert/convert.dart';
import 'package:crypto/crypto.dart';
import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;
import 'package:pub_semver/pub_semver.dart';

/// An update is pinned to one product, platform, release channel and signer.
/// Signing keys MUST be provisioned independently of the update feed.
final class UpdateConfig {
  UpdateConfig({
    required this.appId,
    required this.platform,
    required this.channel,
    required this.currentVersion,
    required this.manifestUri,
    required this.ed25519PublicKeyBase64,
    required this.allowedArtifactHosts,
    this.checkInterval = const Duration(minutes: 2),
    this.maxArtifactBytes = 8 * 1024 * 1024 * 1024,
  }) {
    if (appId.isEmpty || platform.isEmpty || channel.isEmpty ||
        checkInterval <= Duration.zero || maxArtifactBytes <= 0 ||
        !_secure(manifestUri) || allowedArtifactHosts.isEmpty ||
        allowedArtifactHosts.any((host) => host.isEmpty || host != host.toLowerCase())) {
      throw ArgumentError('Invalid updater configuration');
    }
    Version.parse(currentVersion);
    if (base64Decode(ed25519PublicKeyBase64).length != 32) {
      throw ArgumentError('Expected an Ed25519 32-byte public key');
    }
  }

  final String appId;
  final String platform;
  final String channel;
  final String currentVersion;
  final Uri manifestUri;
  final String ed25519PublicKeyBase64;
  final Set<String> allowedArtifactHosts;
  final Duration checkInterval;
  final int maxArtifactBytes;
}

/// An authenticated update candidate. A hash alone is NOT manifest authenticity.
final class UpdateCandidate {
  const UpdateCandidate._({
    required this.version,
    required this.artifactUri,
    required this.sha256Hex,
    required this.sizeBytes,
    required this.artifactId,
    required this.releaseId,
    required this.notes,
  });

  final String version;
  final Uri artifactUri;
  final String sha256Hex;
  final int sizeBytes;
  final String artifactId;
  final String releaseId;
  final String notes;
}

/// Storage is provided by each platform adapter. Implementations must use a
/// private temporary location and atomic promotion on commit.
abstract interface class ArtifactStore {
  Future<ArtifactWriteSession> begin(UpdateCandidate candidate);
}

abstract interface class ArtifactWriteSession {
  Future<void> add(List<int> bytes);
  Future<String> commit();
  Future<void> abort();
}

abstract interface class UpdateInstaller {
  /// Called only after caller consent AND verified streaming SHA-256/size.
  /// The platform adapter must verify signer/publisher and install outcome.
  Future<void> install(VerifiedArtifact artifact);
}

final class VerifiedArtifact {
  const VerifiedArtifact._(this.candidate, this.reference);
  final UpdateCandidate candidate;
  final String reference;
}

final class UpdaterFailure implements Exception {
  const UpdaterFailure(this.reason);
  final String reason;
  @override
  String toString() => 'UpdaterFailure: ' + reason;
}

bool _secure(Uri uri) =>
    uri.scheme == 'https' && uri.host.isNotEmpty &&
    uri.userInfo.isEmpty && !uri.hasFragment;

/// A caller-supplied provider can retrieve short-lived auth credentials
/// from an OS keychain or authenticated broker; never embed access tokens.
typedef UpdateHeaders = Future<Map<String, String>> Function();

/// Intentionally has no automatic installer, timer, CLI, or process exit.
/// Run check() while the app is active; only call install() after user consent.
final class UniversalUpdater {
  UniversalUpdater({
    required this.config,
    required this.store,
    required this.installer,
    http.Client? client,
    UpdateHeaders? headers,
    DateTime Function()? now,
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null,
       _headers = headers,
       _now = now ?? DateTime.now;

  final UpdateConfig config;
  final ArtifactStore store;
  final UpdateInstaller installer;
  final http.Client _client;
  final bool _ownsClient;
  final UpdateHeaders? _headers;
  final DateTime Function() _now;
  DateTime? _nextCheckAt;
  int _failures = 0;
  bool _busy = false;

  DateTime? get nextCheckAt => _nextCheckAt;
  bool get busy => _busy;

  /// Null means unchanged OR skipped by throttle; failures raise an exception.
  /// Error retries back off up to 60 minutes (manual force bypasses throttle).
  Future<UpdateCandidate?> check({bool force = false}) async {
    if (_busy) throw const UpdaterFailure('Another updater operation is running');
    if (!force && _nextCheckAt != null && _now().isBefore(_nextCheckAt!)) {
      return null;
    }
    _busy = true;
    try {
      final request = http.Request('GET', config.manifestUri)
        ..followRedirects = false;
      request.headers['Accept'] = 'application/json';
      request.headers.addAll(await _safeHeaders());
      final response = await _client.send(request);
      if (response.statusCode != 200) {
        throw UpdaterFailure('Update feed unavailable (HTTP ' +
            response.statusCode.toString() + ')');
      }
      final bytes = await _readBounded(response.stream, 64 * 1024);
      final decoded = jsonDecode(utf8.decode(bytes));
      if (decoded is! Map<String, dynamic> ||
          decoded['schema'] != 'aivexus.signed-update.v1' ||
          decoded['payload'] is! String ||
          decoded['signature'] is! String) {
        throw const UpdaterFailure('Invalid signed update envelope');
      }
      final payloadBytes = base64Decode(decoded['payload'] as String);
      if (payloadBytes.length > 32 * 1024) {
        throw const UpdaterFailure('Manifest payload exceeds limit');
      }
      final signatureBytes = base64Decode(decoded['signature'] as String);
      if (signatureBytes.length != 64) {
        throw const UpdaterFailure('Invalid manifest signature length');
      }
      final key = SimplePublicKey(
        base64Decode(config.ed25519PublicKeyBase64),
        type: KeyPairType.ed25519,
      );
      final valid = await Ed25519().verify(
        payloadBytes,
        signature: Signature(signatureBytes, publicKey: key),
      );
      if (!valid) throw const UpdaterFailure('Manifest signature rejected');
      final payload = jsonDecode(utf8.decode(payloadBytes));
      if (payload is! Map<String, dynamic> ||
          payload['app_id'] != config.appId ||
          payload['platform'] != config.platform ||
          payload['channel'] != config.channel ||
          payload['version'] is! String ||
          payload['url'] is! String ||
          payload['size_bytes'] is! int ||
          payload['sha256'] is! String ||
          payload['artifact_id'] is! String ||
          payload['release_id'] is! String) {
        throw const UpdaterFailure('Manifest identity or fields mismatch');
      }
      final version = Version.parse(payload['version'] as String);
      final uri = Uri.tryParse(payload['url'] as String);
      final digest = (payload['sha256'] as String).toLowerCase();
      final size = payload['size_bytes'] as int;
      final artifactId = payload['artifact_id'] as String;
      final releaseId = payload['release_id'] as String;
      if (uri == null || !_secure(uri) ||
          !config.allowedArtifactHosts.contains(uri.host.toLowerCase()) ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(digest) ||
          size <= 0 || size > config.maxArtifactBytes ||
          artifactId.isEmpty || releaseId.isEmpty ||
          artifactId.contains('/') || artifactId.contains(String.fromCharCode(92))) {
        throw const UpdaterFailure('Unsafe signed artifact metadata');
      }
      _failures = 0;
      _nextCheckAt = _now().add(config.checkInterval);
      if (version <= Version.parse(config.currentVersion)) return null;
      return UpdateCandidate._(
        version: version.toString(),
        artifactUri: uri,
        sha256Hex: digest,
        sizeBytes: size,
        artifactId: artifactId,
        releaseId: releaseId,
        notes: (payload['notes'] is String ? payload['notes'] as String : ''),
      );
    } catch (_) {
      _failures = (_failures + 1).clamp(1, 5).toInt();
      final factor = 1 << _failures;
      final minutes = (config.checkInterval.inMinutes * factor).clamp(2, 60).toInt();
      _nextCheckAt = _now().add(Duration(minutes: minutes));
      rethrow;
    } finally {
      _busy = false;
    }
  }

  /// Writes a bounded stream to private staging. An unverified file is never
  /// committed or exposed to installation. No large in-memory installer.
  Future<VerifiedArtifact> download(
    UpdateCandidate candidate, {
    void Function(int received, int total)? onProgress,
  }) async {
    if (_busy) throw const UpdaterFailure('Another updater operation is running');
    if (!_secure(candidate.artifactUri) ||
        !config.allowedArtifactHosts.contains(candidate.artifactUri.host) ||
        candidate.sizeBytes <= 0 || candidate.sizeBytes > config.maxArtifactBytes ||
        !RegExp(r'^[a-f0-9]{64}$').hasMatch(candidate.sha256Hex)) {
      throw const UpdaterFailure('Invalid download target');
    }
    _busy = true;
    ArtifactWriteSession? session;
    try {
      final request = http.Request('GET', candidate.artifactUri)
        ..followRedirects = false;
      request.headers.addAll(await _safeHeaders());
      final response = await _client.send(request);
      if (response.statusCode != 200) {
        throw UpdaterFailure('Installer download unavailable (HTTP ' +
            response.statusCode.toString() + ')');
      }
      session = await store.begin(candidate);
      final digestSink = AccumulatorSink<Digest>();
      final hashInput = sha256.startChunkedConversion(digestSink);
      var count = 0;
      await for (final bytes in response.stream) {
        count += bytes.length;
        if (count > candidate.sizeBytes) {
          throw const UpdaterFailure('Installer exceeds signed size');
        }
        hashInput.add(bytes);
        await session.add(bytes);
        onProgress?.call(count, candidate.sizeBytes);
      }
      hashInput.close();
      if (count != candidate.sizeBytes ||
          digestSink.events.single.toString() != candidate.sha256Hex) {
        throw const UpdaterFailure('Installer size or SHA-256 mismatch');
      }
      final reference = await session.commit();
      if (reference.isEmpty) {
        throw const UpdaterFailure('Staging returned no artifact');
      }
      return VerifiedArtifact._(candidate, reference);
    } catch (_) {
      if (session != null) await session.abort();
      rethrow;
    } finally {
      _busy = false;
    }
  }

  Future<void> install(VerifiedArtifact artifact, {required bool userApproved}) async {
    if (!userApproved) throw const UpdaterFailure('User consent required');
    if (_busy) throw const UpdaterFailure('Another updater operation is running');
    _busy = true;
    try {
      await installer.install(artifact);
    } finally {
      _busy = false;
    }
  }

  Future<Map<String, String>> _safeHeaders() async {
    final supplied = await _headers?.call() ?? <String, String>{};
    if (supplied.keys.any((key) =>
        key.contains('\r') || key.contains('\n')) ||
        supplied.values.any((value) =>
            value.contains('\r') || value.contains('\n'))) {
      throw const UpdaterFailure('Invalid authorization headers');
    }
    return supplied;
  }

  static Future<List<int>> _readBounded(
    Stream<List<int>> input, int maximum,
  ) async {
    final result = <int>[];
    await for (final bytes in input) {
      if (result.length + bytes.length > maximum) {
        throw const UpdaterFailure('Update feed exceeds size limit');
      }
      result.addAll(bytes);
    }
    return result;
  }

  void close() {
    if (_ownsClient) _client.close();
  }
}
