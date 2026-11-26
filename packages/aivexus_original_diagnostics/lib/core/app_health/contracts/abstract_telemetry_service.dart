/// Abstract contract for application-wide telemetry.
///
/// All crash reporting, event logging, error tracking, and performance
/// instrumentation must go through this interface so that the concrete
/// backend (Crashlytics, Sentry, or a local mock) can be swapped without
/// touching any feature or UI code.
abstract class AbstractTelemetryService {
  /// Records an unhandled exception or fatal crash.
  ///
  /// [error]      – the thrown object (Exception, Error, or String)
  /// [stackTrace] – associated stack trace, if available
  /// [context]    – optional free-form label for triage (e.g. 'chat_bloc')
  void logCrash(
    Object error, {
    StackTrace? stackTrace,
    String? context,
  });

  /// Records a discrete application event for usage analytics.
  ///
  /// [name]       – snake_case event name (e.g. 'model_download_started')
  /// [parameters] – optional key/value metadata attached to the event
  void logEvent(
    String name, {
    Map<String, Object>? parameters,
  });

  /// Records a non-fatal error that should be surfaced in the dashboard
  /// without blocking the user.
  ///
  /// [error]      – the thrown or constructed error object
  /// [stackTrace] – associated stack trace, if available
  /// [reason]     – human-readable description of the failure path
  void logError(
    Object error, {
    StackTrace? stackTrace,
    String? reason,
  });

  /// Performance hook — reserved for future instrumentation.
  ///
  /// Start a named trace. Returns a [PerformanceTrace] handle that the
  /// caller must stop when the measured operation completes.
  PerformanceTrace startTrace(String name);
}

/// Lightweight handle returned by [AbstractTelemetryService.startTrace].
///
/// Implementations may wrap platform-specific trace objects (e.g. a
/// Firebase Performance custom trace). The default stub simply records
/// elapsed wall-clock time via [stop].
abstract class PerformanceTrace {
  /// Stops the trace and submits it to the backend, if any.
  void stop();
}
