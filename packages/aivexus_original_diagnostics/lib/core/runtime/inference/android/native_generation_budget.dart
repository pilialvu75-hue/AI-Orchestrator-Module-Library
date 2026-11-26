/// Keeps prompt, output and safety margin within the native context.
abstract final class NativeGenerationBudget {
  static int generationReserve({
    required int context,
    required int promptTokens,
    required int requested,
    required int safetyMargin,
  }) {
    if (promptTokens < 0 || requested < 1) return 0;
    final capacity = context - promptTokens - safetyMargin;
    return capacity <= 0 ? 0 : requested.clamp(1, capacity).toInt();
  }
}
