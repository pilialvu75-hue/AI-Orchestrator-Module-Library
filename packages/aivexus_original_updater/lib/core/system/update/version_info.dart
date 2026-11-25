import 'package:aivexus_original_updater/core/system/update/release_channel.dart';

class VersionInfo {
  const VersionInfo({
    required this.source,
    required this.numericSegments,
    required this.channel,
    required this.preReleaseParts,
  });

  final String source;
  final List<int> numericSegments;
  final ReleaseChannel channel;
  final List<String> preReleaseParts;

  int get major => numericSegments.isNotEmpty ? numericSegments[0] : 0;
  int get minor => numericSegments.length > 1 ? numericSegments[1] : 0;
  int get patch => numericSegments.length > 2 ? numericSegments[2] : 0;

  bool get isPreRelease => preReleaseParts.isNotEmpty;

  String format({bool includePrefix = true}) {
    final base = numericSegments.join('.');
    final suffix = preReleaseParts.isEmpty ? '' : '-${preReleaseParts.join('.')}';
    return '${includePrefix ? 'v' : ''}$base$suffix';
  }

  String get normalizedValue => format(includePrefix: false);
  String get displayValue => format();
}
