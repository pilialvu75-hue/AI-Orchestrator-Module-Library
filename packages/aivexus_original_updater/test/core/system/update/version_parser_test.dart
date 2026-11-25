import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/version_parser.dart';

void main() {
  const parser = VersionParser();

  test('parses prefixed versions with full numeric build segments', () {
    final version = parser.parse('v1.0.12.105');

    expect(version, isNotNull);
    expect(version!.numericSegments, const <int>[1, 0, 12, 105]);
    expect(version.displayValue, 'v1.0.12.105');
    expect(version.channel, ReleaseChannel.stable);
  });

  test('parses beta suffixes and normalizes display values', () {
    final version = parser.parse('1.0.12-beta');

    expect(version, isNotNull);
    expect(version!.displayValue, 'v1.0.12-beta');
    expect(version.channel, ReleaseChannel.beta);
    expect(version.preReleaseParts, const <String>['beta']);
  });

  test('parses build metadata into comparable numeric segments', () {
    final version = parser.parse('1.0.12+105');

    expect(version, isNotNull);
    expect(version!.numericSegments, const <int>[1, 0, 12, 105]);
    expect(version.displayValue, 'v1.0.12.105');
  });

  test('rejects malformed and underspecified versions', () {
    expect(parser.parse('1.0'), isNull);
    expect(parser.parse('1.0.beta'), isNull);
    expect(parser.parse('1..0.1'), isNull);
    expect(parser.parse('v'), isNull);
  });
}
