import 'package:get_it/get_it.dart';

Future<void> configurePlatformUpdateServices(
  GetIt sl, {
  required String currentVersion,
  required String manifestUrl,
  required String githubOwner,
  required String githubRepo,
  required String windowsSetupAssetName,
  required String macosDmgAssetName,
  required String linuxDebAssetName,
}) async {
  // No-op for non-IO targets (for example Flutter Web).
}
