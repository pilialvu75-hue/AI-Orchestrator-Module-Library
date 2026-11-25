enum ReleaseChannel {
  stable,
  beta,
  nightly,
  dev;

  static ReleaseChannel fromString(String? value) {
    switch ((value ?? '').toLowerCase()) {
      case 'beta':
        return ReleaseChannel.beta;
      case 'nightly':
        return ReleaseChannel.nightly;
      case 'dev':
      case 'development':
        return ReleaseChannel.dev;
      case 'stable':
      default:
        return ReleaseChannel.stable;
    }
  }

  String get storageValue => name;

  /// Returns true when this preferred channel allows updates from [other].
  ///
  /// Example:
  /// - beta allows stable + beta
  /// - nightly allows stable + beta + nightly
  bool allows(ReleaseChannel other) =>
      _experimentalRank >= other._experimentalRank;

  int get _experimentalRank => switch (this) {
        ReleaseChannel.stable => 0,
        ReleaseChannel.beta => 1,
        ReleaseChannel.nightly => 2,
        ReleaseChannel.dev => 3,
      };
}
