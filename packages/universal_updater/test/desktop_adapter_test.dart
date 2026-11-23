import 'dart:convert';
import 'dart:io';

import 'package:aivexus_universal_updater/desktop_artifact_store.dart';
import 'package:aivexus_universal_updater/universal_updater.dart';
import 'package:aivexus_universal_updater/windows_installer.dart';
import 'package:crypto/crypto.dart';
import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

void main() {
  late Directory workspace;
  late SimpleKeyPair signing;
  late String publicKey;
  final content = utf8.encode('signed test installer');
  const thumbprint = '0123456789abcdef0123456789abcdef01234567';

  setUp(() async {
    workspace = await Directory.systemTemp.createTemp('updater-test-');
    signing = await Ed25519().newKeyPairFromSeed(List<int>.filled(32, 9));
    publicKey = base64Encode((await signing.extractPublicKey()).bytes);
  });
  tearDown(() async {
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  Future<UniversalUpdater> make(WindowsVerifiedInstaller installer, String root) async {
    final payload = utf8.encode(jsonEncode({
      'app_id': 'voicebridge', 'platform': 'windows-x64',
      'channel': 'beta', 'version': '0.5.6',
      'url': 'https://updates.example.test/setup.exe',
      'size_bytes': content.length,
      'sha256': sha256.convert(content).toString(),
      'artifact_id': 'setup.exe', 'release_id': 'test-056',
    }));
    final signature = await Ed25519().sign(payload, keyPair: signing);
    final envelope = jsonEncode({
      'schema': 'aivexus.signed-update.v1',
      'payload': base64Encode(payload),
      'signature': base64Encode(signature.bytes),
    });
    return UniversalUpdater(
      config: UpdateConfig(
        appId: 'voicebridge', platform: 'windows-x64', channel: 'beta',
        currentVersion: '0.5.5',
        manifestUri: Uri.parse('https://updates.example.test/feed.json'),
        ed25519PublicKeyBase64: publicKey,
        allowedArtifactHosts: {'updates.example.test'},
      ),
      client: MockClient((req) async => req.url.path.endsWith('feed.json')
          ? http.Response(envelope, 200)
          : http.Response.bytes(content, 200)),
      store: DesktopArtifactStore(root),
      installer: installer,
    );
  }

  test('Windows handoff requires staged SHA and pinned signer', () async {
    final root = workspace.path + Platform.pathSeparator + 'staging';
    var signed = false, launched = false;
    final adapter = WindowsVerifiedInstaller(
      stagingRoot: root, pinnedSignerThumbprint: thumbprint,
      isWindows: () => true,
      signerCheck: (file, cert) async {
        signed = true;
        expect(cert, thumbprint.toUpperCase());
        return true;
      },
      launcher: (file) async {
        launched = true;
        expect(await File(file).readAsBytes(), content);
      },
    );
    final engine = await make(adapter, root);
    final downloaded = await engine.download((await engine.check())!);
    await engine.install(downloaded, userApproved: true);
    expect(signed, true);
    expect(launched, true);
  });

  test('a tampered file is never passed to Authenticode or launcher', () async {
    final root = workspace.path + Platform.pathSeparator + 'staging';
    var verified = false, launched = false;
    final adapter = WindowsVerifiedInstaller(
      stagingRoot: root, pinnedSignerThumbprint: thumbprint,
      isWindows: () => true,
      signerCheck: (_, __) async { verified = true; return true; },
      launcher: (_) async { launched = true; },
    );
    final engine = await make(adapter, root);
    final downloaded = await engine.download((await engine.check())!);
    await File(downloaded.reference).writeAsString('tampered');
    await expectLater(
      engine.install(downloaded, userApproved: true),
      throwsA(isA<UpdaterFailure>()),
    );
    expect(verified, false);
    expect(launched, false);
  });

  test('an unsigned or wrong-publisher installer is blocked', () async {
    final root = workspace.path + Platform.pathSeparator + 'staging';
    final adapter = WindowsVerifiedInstaller(
      stagingRoot: root, pinnedSignerThumbprint: thumbprint,
      isWindows: () => true,
      signerCheck: (_, __) async => false,
      launcher: (_) async => fail('must never launch'),
    );
    final engine = await make(adapter, root);
    final downloaded = await engine.download((await engine.check())!);
    await expectLater(
      engine.install(downloaded, userApproved: true),
      throwsA(isA<UpdaterFailure>()),
    );
  });
}
