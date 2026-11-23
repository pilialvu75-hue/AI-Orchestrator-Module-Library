import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import 'src/updater.dart';

typedef SignerCheck = Future<bool> Function(String file, String thumbprint);
typedef InstallerLaunch = Future<void> Function(String file);

/// Windows installer handoff. Requires pinned Authenticode signer. No rollback
/// or success confirmation is claimed: caller must verify next app launch.
final class WindowsVerifiedInstaller implements UpdateInstaller {
  WindowsVerifiedInstaller({
    required this.stagingRoot,
    required this.pinnedSignerThumbprint,
    SignerCheck? signerCheck,
    InstallerLaunch? launcher,
    bool Function()? isWindows,
  }) : _signerCheck = signerCheck ?? _checkAuthenticode,
       _launcher = launcher ?? _launchDetached,
       _isWindows = isWindows ?? _runningWindows {
    if (!RegExp(r'^[A-Fa-f0-9]{40}$').hasMatch(pinnedSignerThumbprint)) {
      throw ArgumentError('Pinned Authenticode signer thumbprint required');
    }
  }

  final String stagingRoot;
  final String pinnedSignerThumbprint;
  final SignerCheck _signerCheck;
  final InstallerLaunch _launcher;
  final bool Function() _isWindows;

  @override
  Future<void> install(VerifiedArtifact artifact) async {
    if (!_isWindows()) throw const UpdaterFailure('Not a Windows platform');
    final file = File(artifact.reference);
    if (!await file.exists() || !file.path.toLowerCase().endsWith('.exe')) {
      throw const UpdaterFailure('Invalid Windows installer');
    }
    final root = await Directory(stagingRoot).resolveSymbolicLinks();
    final actualPath = await file.resolveSymbolicLinks();
    if (!p.isWithin(root, actualPath)) {
      throw const UpdaterFailure('Installer outside staging root');
    }
    if (await file.length() != artifact.candidate.sizeBytes ||
        (await sha256.bind(file.openRead()).first).toString() !=
            artifact.candidate.sha256Hex) {
      throw const UpdaterFailure('Installer changed after download verification');
    }
    if (!await _signerCheck(actualPath, pinnedSignerThumbprint.toUpperCase())) {
      throw const UpdaterFailure('Authenticode signer not trusted');
    }
    await _launcher(actualPath);
  }

  static bool _runningWindows() => Platform.isWindows;

  static Future<void> _launchDetached(String file) async {
    await Process.start(file, const [], mode: ProcessStartMode.detached);
  }

  static Future<bool> _checkAuthenticode(String file, String expected) async {
    final escaped = file.replaceAll("'", "''");
    final script = r'$sig = Get-AuthenticodeSignature -LiteralPath ' +
        "'$escaped'; " +
        r"if ($sig.Status -eq 'Valid' -and $sig.SignerCertificate -and " +
        r"$sig.SignerCertificate.Thumbprint -eq " +
        "'$expected') { exit 0 }; exit 1";
    final result = await Process.run(
      'powershell.exe',
      <String>['-NoProfile', '-NonInteractive', '-Command', script],
    );
    return result.exitCode == 0;
  }
}
