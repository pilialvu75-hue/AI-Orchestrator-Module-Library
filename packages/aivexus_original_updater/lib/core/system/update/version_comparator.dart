import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/version_info.dart';
import 'package:aivexus_original_updater/core/system/update/version_parser.dart';

class VersionComparator {
  const VersionComparator({VersionParser parser = const VersionParser()})
      : _parser = parser;

  final VersionParser _parser;

  VersionInfo? parse(String version) => _parser.parse(version);

  String? normalize(
    String version, {
    bool includePrefix = true,
  }) {
    return _parser.normalize(version, includePrefix: includePrefix);
  }

  int compare(String left, String right) {
    final a = parse(left);
    final b = parse(right);

    if (a == null && b == null) return 0;
    if (a == null) return -1;
    if (b == null) return 1;

    // Compare the application version before channel and beta sequence.
    // Windows package_info adds the file build as a fourth numeric segment;
    // that build must not make beta.4 newer than beta.5 or than stable.
    for (var index = 0; index < 3; index += 1) {
      final leftSegment = index < a.numericSegments.length
          ? a.numericSegments[index]
          : 0;
      final rightSegment = index < b.numericSegments.length
          ? b.numericSegments[index]
          : 0;
      final segmentCmp = leftSegment.compareTo(rightSegment);
      if (segmentCmp != 0) {
        return segmentCmp;
      }
    }

    if (!a.isPreRelease && !b.isPreRelease) {
      return _compareBuildRevisions(a, b);
    }
    if (!a.isPreRelease) {
      return 1;
    }
    if (!b.isPreRelease) {
      return -1;
    }

    final channelCmp =
        _stabilityRank(a.channel).compareTo(_stabilityRank(b.channel));
    if (channelCmp != 0) {
      return channelCmp;
    }

    final prerelease = _comparePreReleaseParts(a.preReleaseParts, b.preReleaseParts);
    return prerelease != 0 ? prerelease : _compareBuildRevisions(a, b);
  }

  int _compareBuildRevisions(VersionInfo a, VersionInfo b) {
    final length = a.numericSegments.length > b.numericSegments.length
        ? a.numericSegments.length : b.numericSegments.length;
    for (var index = 3; index < length; index++) {
      final left = index < a.numericSegments.length ? a.numericSegments[index] : 0;
      final right = index < b.numericSegments.length ? b.numericSegments[index] : 0;
      final compared = left.compareTo(right);
      if (compared != 0) return compared;
    }
    return 0;
  }

  bool isNewer({required String latest, required String current}) =>
      compare(latest, current) > 0;

  bool isCompatible({required String currentVersion, required String minSupported}) =>
      compare(currentVersion, minSupported) >= 0;

  int _comparePreReleaseParts(List<String> left, List<String> right) {
    final maxLength = left.length > right.length ? left.length : right.length;
    for (var index = 0; index < maxLength; index += 1) {
      if (index >= left.length) {
        return -1;
      }
      if (index >= right.length) {
        return 1;
      }

      final leftPart = left[index];
      final rightPart = right[index];
      final leftNumber = int.tryParse(leftPart);
      final rightNumber = int.tryParse(rightPart);
      if (leftNumber != null && rightNumber != null) {
        final compare = leftNumber.compareTo(rightNumber);
        if (compare != 0) {
          return compare;
        }
        continue;
      }
      if (leftNumber != null) {
        return -1;
      }
      if (rightNumber != null) {
        return 1;
      }

      final compare = leftPart.compareTo(rightPart);
      if (compare != 0) {
        return compare;
      }
    }
    return 0;
  }

  int _stabilityRank(ReleaseChannel channel) => switch (channel) {
        ReleaseChannel.dev => 0,
        ReleaseChannel.nightly => 1,
        ReleaseChannel.beta => 2,
        ReleaseChannel.stable => 3,
      };
}
