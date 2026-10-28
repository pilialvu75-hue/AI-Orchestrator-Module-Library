import Foundation
import Diagnostics

/// Native macOS implementation of the diagnostics.logging.v1 logical boundary.
/// No upload, remote transport, console capture or entitlement escalation.
public enum AivexusSeverity: String, Sendable {
    case debug
    case info
    case warning
    case error
}

public enum AivexusLoggingError: Error, Equatable {
    case notInitialized
    case emptyMessage
    case oversizedMessage
}

public enum AivexusDiagnosticsLoggingBridge {
    public static let maxMessageBytes = 4096

    /// Initializes the pinned Diagnostics dependency on its supported target.
    public static func initialize() throws {
        try DiagnosticsLogger.setup()
        guard DiagnosticsLogger.isSetUp() else {
            throw AivexusLoggingError.notInitialized
        }
    }

    /// Accepts a bounded event and sends only its redacted text to Diagnostics.
    /// This does not imply that arbitrary PII has been detected.
    @discardableResult
    public static func log(
        _ message: String,
        severity: AivexusSeverity = .info
    ) throws -> String {
        guard DiagnosticsLogger.isSetUp() else {
            throw AivexusLoggingError.notInitialized
        }
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw AivexusLoggingError.emptyMessage
        }
        guard trimmed.utf8.count <= maxMessageBytes else {
            throw AivexusLoggingError.oversizedMessage
        }
        let redacted = redactKnownSecrets(trimmed)
        DiagnosticsLogger.log(message: "[AIVEXUS/\(severity.rawValue)] \(redacted)")
        return redacted
    }

    public static func redactKnownSecrets(_ text: String) -> String {
        let patterns: [(String, String)] = [
            (#"(?i)\b(token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"#,
             "$1=[REDACTED]"),
            (#"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;]+"#,
             "authorization: bearer [REDACTED]")
        ]
        var result = text
        for (pattern, replacement) in patterns {
            guard let expression = try? NSRegularExpression(pattern: pattern) else {
                continue
            }
            result = expression.stringByReplacingMatches(
                in: result,
                options: [],
                range: NSRange(result.startIndex..<result.endIndex, in: result),
                withTemplate: replacement
            )
        }
        return result
    }
}
