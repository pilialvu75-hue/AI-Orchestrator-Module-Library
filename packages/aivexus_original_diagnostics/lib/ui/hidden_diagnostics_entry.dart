import 'dart:async';
import 'package:flutter/material.dart';
import 'diagnostics_console_page.dart';

/// Wrap a host-chosen, otherwise non-interactive visible element (e.g. version
/// label). Seven taps within five seconds open the local technical console.
/// Not an authentication mechanism; no secrets or user content are displayed.
class HiddenDiagnosticsEntry extends StatefulWidget {
  const HiddenDiagnosticsEntry({super.key, required this.child, this.enabled = true});
  final Widget child;
  final bool enabled;

  @override
  State<HiddenDiagnosticsEntry> createState() => _HiddenDiagnosticsEntryState();
}

class _HiddenDiagnosticsEntryState extends State<HiddenDiagnosticsEntry> {
  Timer? _reset;
  int _taps = 0;
  bool _open = false;

  void _clear() {
    _reset?.cancel();
    _reset = null;
    _taps = 0;
  }

  Future<void> _tap() async {
    if (!widget.enabled || _open) return;
    if (_taps == 0) _reset = Timer(const Duration(seconds: 5), _clear);
    if (++_taps < 7) return;
    _clear();
    _open = true;
    try {
      await Navigator.of(context).push<void>(MaterialPageRoute(
        builder: (_) => const DiagnosticsConsolePage(),
      ));
    } finally {
      _open = false;
    }
  }

  @override
  void didUpdateWidget(covariant HiddenDiagnosticsEntry oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.enabled) _clear();
  }

  @override
  void dispose() {
    _clear();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
    behavior: HitTestBehavior.opaque, onTap: widget.enabled ? _tap : null,
    child: widget.child,
  );
}
