import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/version_info.dart';

class VersionParser {
  const VersionParser();

  VersionInfo? parse(String version) {
    final trimmed = version.trim();
    if (trimmed.isEmpty) {
      return null;
    }

    var working = trimmed;
    if (working.startsWith('v') || working.startsWith('V')) {
      working = working.substring(1);
    }

    String? buildMetadata;
    final plusIndex = working.indexOf('+');
    if (plusIndex >= 0) {
      buildMetadata = working.substring(plusIndex + 1).trim();
      working = working.substring(0, plusIndex).trim();
    }

    String? preRelease;
    final hyphenIndex = working.indexOf('-');
    if (hyphenIndex >= 0) {
      preRelease = working.substring(hyphenIndex + 1).trim();
      working = working.substring(0, hyphenIndex).trim();
    }

    final numericParts = working.split('.');
    if (numericParts.length < 3) {
      return null;
    }

    final numericSegments = <int>[];
    for (final part in numericParts) {
      final value = int.tryParse(part);
      if (value == null) {
        return null;
      }
      numericSegments.add(value);
    }

    if (buildMetadata != null && buildMetadata.isNotEmpty) {
      final buildParts = buildMetadata.split('.');
      for (final part in buildParts) {
        final value = int.tryParse(part.trim());
        if (value == null) {
          return null;
        }
        numericSegments.add(value);
      }
    }

    final preReleaseParts = <String>[];
    if (preRelease != null && preRelease.isNotEmpty) {
      for (final part in preRelease.split('.')) {
        final normalized = part.trim().toLowerCase();
        if (normalized.isEmpty) {
          return null;
        }
        preReleaseParts.add(normalized);
      }
    }

    return VersionInfo(
      source: trimmed,
      numericSegments: List<int>.unmodifiable(numericSegments),
      channel: _channelForParts(preReleaseParts),
      preReleaseParts: List<String>.unmodifiable(preReleaseParts),
    );
  }

  String? normalize(
    String version, {
    bool includePrefix = true,
  }) {
    return parse(version)?.format(includePrefix: includePrefix);
  }

  ReleaseChannel _channelForParts(List<String> preReleaseParts) {
    if (preReleaseParts.isEmpty) {
      return ReleaseChannel.stable;
    }

    return switch (preReleaseParts.first) {
      'stable' => ReleaseChannel.stable,
      'beta' => ReleaseChannel.beta,
      'nightly' => ReleaseChannel.nightly,
      'dev' => ReleaseChannel.dev,
      _ => ReleaseChannel.dev,
    };
  }
}
