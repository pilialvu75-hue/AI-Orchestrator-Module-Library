import 'dart:convert';

import 'package:aivexus_universal_updater/universal_updater.dart';
import 'package:crypto/crypto.dart';
import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

final class _MemoryStore implements ArtifactStore {
  _Writer? writer;
  @override
  Future<ArtifactWriteSession> begin(UpdateCandidate candidate) async {
    writer = _Writer();
    return writer!;
  }
}

final class _Writer implements ArtifactWriteSession {
  final bytes = <int>[];
  bool aborted = false;
  bool committed = false;
  @override
  Future<void> add(List<int> chunk) async => bytes.addAll(chunk);
  @override
  Future<String> commit() async {
    committed = true;
    return 'memory:verified';
  }
  @override
  Future<void> abort() async { aborted = true; }
}

final class _Installer implements UpdateInstaller {
  bool called = false;
  @override
  Future<void> install(VerifiedArtifact artifact) async { called = true; }
}

void main() {
  late SimpleKeyPair signing;
  late String publicKey;
  final sample = utf8.encode('verified installer');

  setUp(() async {
    signing = await Ed25519().newKeyPairFromSeed(List<int>.filled(32, 7));
    publicKey = base64Encode((await signing.extractPublicKey()).bytes);
  });

  UpdateConfig config({String app = 'voicebridge', String current = '0.5.5'}) =>
      UpdateConfig(
        appId: app,
        platform: 'windows-x64',
        channel: 'beta',
        currentVersion: current,
        manifestUri: Uri.parse('https://updates.example.test/feed.json'),
        ed25519PublicKeyBase64: publicKey,
        allowedArtifactHosts: {'updates.example.test'},
      );

  Future<String> envelope({
    String app = 'voicebridge',
    String version = '0.5.6',
    String? digest,
  }) async {
    final payload = utf8.encode(jsonEncode({
      'app_id': app,
      'platform': 'windows-x64',
      'channel': 'beta',
      'version': version,
      'url': 'https://updates.example.test/setup.exe',
      'size_bytes': sample.length,
      'sha256': digest ?? sha256.convert(sample).toString(),
      'artifact_id': 'setup.exe',
      'release_id': 'beta-056',
      'notes': 'test beta',
    }));
    final signature = await Ed25519().sign(payload, keyPair: signing);
    return jsonEncode({
      'schema': 'aivexus.signed-update.v1',
      'payload': base64Encode(payload),
      'signature': base64Encode(signature.bytes),
    });
  }

  test('signed update -> SHA-verified stage -> explicit install consent', () async {
    final signed = await envelope();
    final store = _MemoryStore();
    final installer = _Installer();
    final client = MockClient((req) async {
      if (req.url.path.endsWith('feed.json')) {
        return http.Response(signed, 200);
      }
      return http.Response.bytes(sample, 200);
    });
    final updater = UniversalUpdater(
      config: config(), client: client, store: store, installer: installer,
    );
    final candidate = await updater.check();
    expect(candidate?.version, '0.5.6');
    final staged = await updater.download(candidate!);
    expect(store.writer!.committed, true);
    expect(store.writer!.bytes, sample);
    await expectLater(
      updater.install(staged, userApproved: false),
      throwsA(isA<UpdaterFailure>()),
    );
    expect(installer.called, false);
    await updater.install(staged, userApproved: true);
    expect(installer.called, true);
  });

  test('wrong product identity is rejected even with valid signature', () async {
    final signed = await envelope(app: 'other_app');
    final updater = UniversalUpdater(
      config: config(),
      client: MockClient((_) async => http.Response(signed, 200)),
      store: _MemoryStore(),
      installer: _Installer(),
    );
    await expectLater(updater.check(), throwsA(isA<UpdaterFailure>()));
  });

  test('tampered signature cannot produce an update', () async {
    final signed = jsonDecode(await envelope()) as Map<String, dynamic>;
    signed['payload'] = base64Encode(utf8.encode('{"app_id":"voicebridge"}'));
    final updater = UniversalUpdater(
      config: config(),
      client: MockClient((_) async => http.Response(jsonEncode(signed), 200)),
      store: _MemoryStore(),
      installer: _Installer(),
    );
    await expectLater(updater.check(), throwsA(isA<UpdaterFailure>()));
  });

  test('wrong downloaded SHA is rejected and staged data is aborted', () async {
    final signed = await envelope(digest: List<String>.filled(64, 'a').join());
    final store = _MemoryStore();
    final updater = UniversalUpdater(
      config: config(),
      client: MockClient((req) async => req.url.path.endsWith('feed.json')
          ? http.Response(signed, 200)
          : http.Response.bytes(sample, 200)),
      store: store, installer: _Installer(),
    );
    final candidate = await updater.check();
    await expectLater(updater.download(candidate!), throwsA(isA<UpdaterFailure>()));
    expect(store.writer!.aborted, true);
    expect(store.writer!.committed, false);
  });

  test('never offers downgrade and throttles successful repeat checks', () async {
    var requests = 0;
    final signed = await envelope(version: '0.5.4');
    final updater = UniversalUpdater(
      config: config(),
      client: MockClient((_) async { requests++; return http.Response(signed, 200); }),
      store: _MemoryStore(), installer: _Installer(),
    );
    expect(await updater.check(), isNull);
    expect(await updater.check(), isNull);
    expect(requests, 1);
  });

  test('HTTP 403 is an error, never "up to date"', () async {
    final updater = UniversalUpdater(
      config: config(),
      client: MockClient((_) async => http.Response('forbidden', 403)),
      store: _MemoryStore(), installer: _Installer(),
    );
    await expectLater(updater.check(), throwsA(isA<UpdaterFailure>()));
    expect(updater.nextCheckAt, isNotNull);
  });

  test('rejects missing identity configuration and insecure feed', () {
    expect(() => UpdateConfig(
      appId: 'voicebridge', platform: 'windows-x64', channel: 'beta',
      currentVersion: '0.5.5',
      manifestUri: Uri.parse('http://updates.example.test/feed.json'),
      ed25519PublicKeyBase64: publicKey,
      allowedArtifactHosts: {'updates.example.test'},
    ), throwsArgumentError);
  });
}
