import 'package:equatable/equatable.dart';

/// Base class for all domain-layer failures.
abstract class Failure extends Equatable {
  const Failure([this.message = '']);

  final String message;

  @override
  List<Object> get props => [message];
}

/// Failure originating from a local database operation.
class DatabaseFailure extends Failure {
  const DatabaseFailure([super.message]);
}

/// Failure originating from a remote API call (OpenAI / Gemini).
class ServerFailure extends Failure {
  const ServerFailure([super.message]);
}

enum CloudFailureKind {
  authentication,
  rateLimit,
  quota,
  providerUnavailable,
  network,
  timeout,
  incompleteOutput,
  emptyOutput,
  unsupported,
  other,
}

/// Structured Cloud failure used by routing, health and diagnostics.
class CloudFailure extends Failure {
  const CloudFailure(
    super.message, {
    required this.kind,
    this.statusCode,
    this.retryable = false,
    this.retryAfter,
  });

  final CloudFailureKind kind;
  final int? statusCode;
  final bool retryable;
  final Duration? retryAfter;

  @override
  List<Object> get props => <Object>[
        ...super.props,
        kind,
        if (statusCode != null) statusCode!,
        retryable,
        if (retryAfter != null) retryAfter!,
      ];
}

/// Failure when the device has no network connection.
class NetworkFailure extends Failure {
  const NetworkFailure([super.message]);
}

/// Failure when a requested entity cannot be found.
class NotFoundFailure extends Failure {
  const NotFoundFailure([super.message]);
}

/// Failure when a provided value is invalid.
class ValidationFailure extends Failure {
  const ValidationFailure([super.message]);
}

/// Failure when an Android Intent operation fails.
class IntentFailure extends Failure {
  const IntentFailure([super.message]);
}

/// Failure when a file download operation fails.
class DownloadFailure extends Failure {
  const DownloadFailure([super.message]);
}

/// Failure when a required device permission is denied.
class PermissionFailure extends Failure {
  const PermissionFailure([super.message]);
}
