import XCTest
import Diagnostics
@testable import AivexusDiagnosticsLoggingBridge

final class AivexusDiagnosticsBridgeTests: XCTestCase {
    func testCaptureIsDisabledUnlessCallerExplicitlyOptsIn() {
        XCTAssertThrowsError(
            try AivexusDiagnosticsLoggingBridge.initialize()
        ) { error in
            XCTAssertEqual(
                error as? AivexusLoggingError,
                .explicitCaptureAuthorizationRequired
            )
        }
    }

    func testBootAndRealLoggingThroughPinnedDependency() throws {
        try AivexusDiagnosticsLoggingBridge.initialize(allowProcessWideLogCapture: true)
        XCTAssertTrue(DiagnosticsLogger.isSetUp())
        let rendered = try AivexusDiagnosticsLoggingBridge.log(
            "bridge integration event", severity: .info
        )
        XCTAssertEqual(rendered, "bridge integration event")
    }

    func testSecretRedactionBeforeForwarding() throws {
        try AivexusDiagnosticsLoggingBridge.initialize(allowProcessWideLogCapture: true)
        let rendered = try AivexusDiagnosticsLoggingBridge.log(
            "password=private-123 token: AB12 authorization: Bearer my-token"
        )
        XCTAssertFalse(rendered.contains("private-123"))
        XCTAssertFalse(rendered.contains("AB12"))
        XCTAssertFalse(rendered.contains("my-token"))
        XCTAssertTrue(rendered.contains("password=[REDACTED]"))
        XCTAssertTrue(rendered.contains("token=[REDACTED]"))
    }

    func testEmptyInputFailsWithoutSending() throws {
        try AivexusDiagnosticsLoggingBridge.initialize(allowProcessWideLogCapture: true)
        XCTAssertThrowsError(try AivexusDiagnosticsLoggingBridge.log("  \n ")) { error in
            XCTAssertEqual(error as? AivexusLoggingError, .emptyMessage)
        }
    }

    func testOversizeFailsWithoutSending() throws {
        try AivexusDiagnosticsLoggingBridge.initialize(allowProcessWideLogCapture: true)
        XCTAssertThrowsError(
            try AivexusDiagnosticsLoggingBridge.log(
                String(repeating: "x", count: AivexusDiagnosticsLoggingBridge.maxMessageBytes + 1)
            )
        ) { error in
            XCTAssertEqual(error as? AivexusLoggingError, .oversizedMessage)
        }
    }

    func testKnownSecretPatternIsExplicitlyLimited() {
        XCTAssertEqual(
            AivexusDiagnosticsLoggingBridge.redactKnownSecrets("password=A1"),
            "password=[REDACTED]"
        )
        XCTAssertEqual(
            AivexusDiagnosticsLoggingBridge.redactKnownSecrets("public message"),
            "public message"
        )
    }
}
