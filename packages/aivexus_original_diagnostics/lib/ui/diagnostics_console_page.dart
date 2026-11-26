import 'package:aivexus_original_diagnostics/src/diagnostics.dart';
import 'package:aivexus_original_diagnostics/src/resource_diagnostics_page.dart';
import 'dart:async';
import 'application_diagnostics_page.dart';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:aivexus_original_diagnostics/core/runtime/inference/runtime_event_log.dart';

/// Full-screen diagnostics console that displays live runtime inference events.
///
/// Events are captured by [RuntimeEventLog] as the pipeline runs.  The view
/// updates in real time via a [StreamBuilder] and auto-scrolls to the latest
/// entry.
///
/// Users can filter by [RuntimeEventCategory], clear the buffer, or copy all
/// entries to the clipboard.
class DiagnosticsConsolePage extends StatefulWidget {
  const DiagnosticsConsolePage({super.key});

  @override
  State<DiagnosticsConsolePage> createState() => _DiagnosticsConsolePageState();
}

class _DiagnosticsConsolePageState extends State<DiagnosticsConsolePage> {
  final _log = RuntimeEventLog.instance;
  final _scrollController = ScrollController();

  /// Currently selected category filter; `null` means "show all".
  RuntimeEventCategory? _filterCategory;

  /// Snapshot of entries at the time of the last rebuild.
  List<RuntimeEventEntry> _filtered = [];

  /// Whether the view should auto-scroll to the bottom when new entries arrive.
  bool _autoScroll = true;

  late StreamSubscription<RuntimeEventEntry> _entrySub;
  late StreamSubscription<void> _clearSub;

  @override
  void initState() {
    super.initState();
    _filtered = _applyFilter(_log.entries);
    _entrySub = _log.stream.listen(_onNewEntry);
    _clearSub = _log.onClear.listen((_) {
      if (!mounted) return;
      setState(() => _filtered = []);
    });
  }

  @override
  void dispose() {
    _entrySub.cancel();
    _clearSub.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  void _onNewEntry(RuntimeEventEntry entry) {
    if (!mounted) return;
    if (!AivexusDiagnostics.isSafeEntry(entry)) return;
    if (_filterCategory != null && entry.category != _filterCategory) return;
    // Rebuild from the bounded original buffer, rather than an unbounded UI list.
    setState(() => _filtered = _applyFilter(_log.entries));
    if (_autoScroll) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) return;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
    );
  }

  List<RuntimeEventEntry> _applyFilter(List<RuntimeEventEntry> all) {
    return all.where((e) => AivexusDiagnostics.isSafeEntry(e) &&
      (_filterCategory == null || e.category == _filterCategory)).toList();
  }

  void _setFilter(RuntimeEventCategory? cat) {
    setState(() {
      _filterCategory = cat;
      _filtered = _applyFilter(_log.entries);
    });
    if (_autoScroll) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
    }
  }

  Future<void> _copyAll() async {
    final text = _filtered.map((e) => e.toString()).join('\n');
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Log copied to clipboard'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  Future<void> _showHistory() async {
    final history = await AivexusDiagnostics.instance.readSafeHistory();
    if (!mounted) return;
    await showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('Local history'),
      content: SingleChildScrollView(child: SelectableText(
        history.isEmpty ? 'No retained events' : history)),
      actions: [
        TextButton(onPressed: history.isEmpty ? null : () async {
          await Clipboard.setData(ClipboardData(text: history));
          if (context.mounted) Navigator.pop(context);
        }, child: const Text('Copy')),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
      ],
    ));
  }

  Future<void> _clearLog() async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Clear local diagnostics?'),
      content: const Text('This removes the retained diagnostic history.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Clear')),
      ],
    ));
    if (confirmed != true || !mounted) return;
    await AivexusDiagnostics.instance.clear();
    if (mounted) setState(() => _filtered = []);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
        title: const Text(
          'Runtime Diagnostics',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
        ),
        actions: [
          IconButton(
            tooltip: 'Local history',
            icon: const Icon(Icons.history, color: Colors.white),
            onPressed: _showHistory,
          ),
          IconButton(
            tooltip: 'Resources',
            icon: const Icon(Icons.memory, color: Colors.white),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => const ResourceDiagnosticsPage(),
            )),
          ),
          IconButton(
            tooltip: 'Application information',
            icon: const Icon(Icons.info_outline, color: Colors.white),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ApplicationDiagnosticsPage())),
          ),
          // Auto-scroll toggle
          IconButton(
            tooltip: _autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF',
            icon: Icon(
              _autoScroll
                  ? Icons.vertical_align_bottom_rounded
                  : Icons.vertical_align_center_rounded,
              color: _autoScroll ? const Color(0xFF34D399) : Colors.white38,
            ),
            onPressed: () => setState(() => _autoScroll = !_autoScroll),
          ),
          // Copy button
          IconButton(
            tooltip: 'Copy all entries',
            icon: const Icon(Icons.copy_outlined, color: Colors.white),
            onPressed: _filtered.isEmpty ? null : _copyAll,
          ),
          // Clear button
          IconButton(
            tooltip: 'Clear log',
            icon: const Icon(Icons.delete_outline, color: Colors.white),
            onPressed: _clearLog,
          ),
        ],
      ),
      body: Column(
        children: [
          // ── Category filter chips ────────────────────────────────────────────
          _CategoryFilterBar(
            selected: _filterCategory,
            onSelected: _setFilter,
          ),
          const Divider(height: 1, color: Color(0xFF1F2937)),
          // ── Entry count indicator ────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Row(
              children: [
                Text(
                  '${_filtered.length} event${_filtered.length == 1 ? '' : 's'}',
                  style: const TextStyle(
                    color: Color(0xFF6B7280),
                    fontSize: 11,
                  ),
                ),
                const Spacer(),
                const Text(
                  'buffer max ${RuntimeEventLog.maxEntries}',
                  style: TextStyle(
                    color: Color(0xFF374151),
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
          // ── Log entries ──────────────────────────────────────────────────────
          Expanded(
            child: _filtered.isEmpty
                ? const Center(
                    child: Text(
                      'No runtime events captured yet.\n'
                      'Diagnostic events will appear automatically.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Color(0xFF4B5563), height: 1.6),
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(8, 4, 8, 16),
                    itemCount: _filtered.length,
                    itemBuilder: (context, index) =>
                        _EntryRow(entry: _filtered[index]),
                  ),
          ),
        ],
      ),
    );
  }
}

// ── Category filter bar ───────────────────────────────────────────────────────

class _CategoryFilterBar extends StatelessWidget {
  const _CategoryFilterBar({
    required this.selected,
    required this.onSelected,
  });

  final RuntimeEventCategory? selected;
  final void Function(RuntimeEventCategory?) onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 42,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        children: [
          _FilterChip(
            label: 'All',
            color: const Color(0xFF6B7280),
            selected: selected == null,
            onTap: () => onSelected(null),
          ),
          ...RuntimeEventCategory.values.map(
            (cat) => _FilterChip(
              label: _labelFor(cat),
              color: _colorFor(cat),
              selected: selected == cat,
              onTap: () => onSelected(selected == cat ? null : cat),
            ),
          ),
        ],
      ),
    );
  }

  static String _labelFor(RuntimeEventCategory cat) {
    switch (cat) {
      case RuntimeEventCategory.model:
        return 'MODEL';
      case RuntimeEventCategory.runtime:
        return 'RUNTIME';
      case RuntimeEventCategory.inference:
        return 'INFERENCE';
      case RuntimeEventCategory.fallback:
        return 'FALLBACK';
      case RuntimeEventCategory.token:
        return 'TOKEN';
      case RuntimeEventCategory.stream:
        return 'STREAM';
      case RuntimeEventCategory.validation:
        return 'VALIDATION';
      case RuntimeEventCategory.websearch:
        return 'WEBSEARCH';
      case RuntimeEventCategory.hardware:
        return 'HARDWARE';
      case RuntimeEventCategory.voice:
        return 'VOICE';
      case RuntimeEventCategory.other:
        return 'OTHER';
    }
  }

  static Color _colorFor(RuntimeEventCategory cat) {
    switch (cat) {
      case RuntimeEventCategory.model:
        return const Color(0xFF60A5FA); // blue
      case RuntimeEventCategory.runtime:
        return const Color(0xFFFB923C); // orange
      case RuntimeEventCategory.inference:
        return const Color(0xFF34D399); // green
      case RuntimeEventCategory.fallback:
        return const Color(0xFFF87171); // red
      case RuntimeEventCategory.token:
        return const Color(0xFF2DD4BF); // teal
      case RuntimeEventCategory.stream:
        return const Color(0xFF22D3EE); // cyan
      case RuntimeEventCategory.validation:
        return const Color(0xFFA78BFA); // purple
      case RuntimeEventCategory.websearch:
        return const Color(0xFFF59E0B); // amber
      case RuntimeEventCategory.hardware:
        return const Color(0xFF38BDF8); // sky
      case RuntimeEventCategory.voice:
        return const Color(0xFFF472B6); // pink
      case RuntimeEventCategory.other:
        return const Color(0xFF9CA3AF); // grey
    }
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
          decoration: BoxDecoration(
            color: selected
                ? color.withValues(alpha: 0.2)
                : const Color(0xFF1F2937),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected ? color : const Color(0xFF374151),
              width: selected ? 1.5 : 1,
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? color : const Color(0xFF9CA3AF),
              fontSize: 11,
              fontWeight:
                  selected ? FontWeight.w600 : FontWeight.normal,
              letterSpacing: 0.5,
            ),
          ),
        ),
      ),
    );
  }
}

// ── Single log entry row ──────────────────────────────────────────────────────

class _EntryRow extends StatelessWidget {
  const _EntryRow({required this.entry});

  final RuntimeEventEntry entry;

  @override
  Widget build(BuildContext context) {
    final tagColor = _colorFor(entry.category);
    final ts = _formatTimestamp(entry.timestamp);
    // Trim the leading [TAG] from the message since we display it separately.
    final body = entry.message.startsWith('[${entry.tag}]')
        ? entry.message.substring('[${entry.tag}]'.length).trimLeft()
        : entry.message;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timestamp
          SizedBox(
            width: 68,
            child: Text(
              ts,
              style: const TextStyle(
                color: Color(0xFF374151),
                fontSize: 9.5,
                fontFamily: 'monospace',
              ),
            ),
          ),
          const SizedBox(width: 4),
          // Tag badge
          Container(
            constraints: const BoxConstraints(minWidth: 96),
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: tagColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              '[${entry.tag}]',
              style: TextStyle(
                color: tagColor,
                fontSize: 10,
                fontFamily: 'monospace',
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: 6),
          // Message body
          Expanded(
            child: Text(
              body,
              style: const TextStyle(
                color: Color(0xFFD1D5DB),
                fontSize: 10.5,
                fontFamily: 'monospace',
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _formatTimestamp(DateTime dt) {
    final ms = dt.millisecond.toString().padLeft(3, '0');
    return '${_pad(dt.hour)}:${_pad(dt.minute)}:${_pad(dt.second)}.$ms';
  }

  static String _pad(int v) => v.toString().padLeft(2, '0');

  static Color _colorFor(RuntimeEventCategory cat) {
    switch (cat) {
      case RuntimeEventCategory.model:
        return const Color(0xFF60A5FA);
      case RuntimeEventCategory.runtime:
        return const Color(0xFFFB923C);
      case RuntimeEventCategory.inference:
        return const Color(0xFF34D399);
      case RuntimeEventCategory.fallback:
        return const Color(0xFFF87171);
      case RuntimeEventCategory.token:
        return const Color(0xFF2DD4BF);
      case RuntimeEventCategory.stream:
        return const Color(0xFF22D3EE);
      case RuntimeEventCategory.validation:
        return const Color(0xFFA78BFA);
      case RuntimeEventCategory.websearch:
        return const Color(0xFFF59E0B);
      case RuntimeEventCategory.hardware:
        return const Color(0xFF38BDF8);
      case RuntimeEventCategory.voice:
        return const Color(0xFFF472B6);
      case RuntimeEventCategory.other:
        return const Color(0xFF9CA3AF);
    }
  }
}
