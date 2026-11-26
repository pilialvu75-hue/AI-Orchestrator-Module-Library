import 'package:flutter/material.dart';
import '../src/diagnostics.dart';
import '../src/diagnostic_delivery.dart';
import '../src/diagnostic_report.dart';
import '../src/diagnostic_labels.dart';

/// Host may expose this page ONLY when an approved private receiver is
/// configured. This widget does not construct an endpoint or auto-send.
class DiagnosticDeliveryPage extends StatefulWidget {
  const DiagnosticDeliveryPage({super.key, required this.delivery});
  final DiagnosticDelivery delivery;
  @override
  State<DiagnosticDeliveryPage> createState() => _DiagnosticDeliveryPageState();
}

class _DiagnosticDeliveryPageState extends State<DiagnosticDeliveryPage> {
  bool _busy = false;
  String? _notice;
  DiagnosticDelivery get delivery => widget.delivery;
  String tr(String key) => diagnosticLabel(context, key);

  Future<void> run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() { _busy = true; _notice = null; });
    try { await action(); }
    catch (_) { if (mounted) setState(() => _notice = 'Delivery unavailable'); }
    finally { if (mounted) setState(() => _busy = false); }
  }

  Future<void> prepare() async {
    final report = DiagnosticReport.fromSafeHistory(
      await AivexusDiagnostics.instance.readSafeHistory());
    if (!mounted) return;
    if (report.events.isEmpty) {
      setState(() => _notice = 'No retained events');
      return;
    }
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(diagnosticLabel(context, 'Approve diagnostic report?')),
        content: SingleChildScrollView(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(diagnosticLabel(context, 'Destination')),
            SelectableText(delivery.endpoint.toString()),
            const SizedBox(height: 12),
            Text(diagnosticLabel(context, 'Only this filtered snapshot will be queued. Approval expires after 24 hours.')),
            const SizedBox(height: 12),
            SelectableText(report.json),
          ],
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false),
            child: Text(diagnosticLabel(context, 'Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(context, true),
            child: Text(diagnosticLabel(context, 'Approve snapshot'))),
        ],
      ),
    );
    if (approved != true || !mounted) return;
    final queued = await delivery.queueApproved(report, consent: true);
    if (!queued && mounted) setState(() => _notice = 'Could not queue report. An approved report may already exist.');
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(tr('Diagnostic delivery'))),
    body: ListenableBuilder(listenable: delivery, builder: (_, __) => ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(tr('Destination'), style: Theme.of(context).textTheme.titleMedium),
        SelectableText(delivery.endpoint.toString()),
        const SizedBox(height: 12),
        Text(tr('No automatic transmission. Review and approve a report before sending.')),
        ListTile(title: Text(tr('Status')), subtitle: Text(tr('delivery_${delivery.state.name}'))),
        if (_notice != null) Text(tr(_notice!)),
        FilledButton(onPressed: _busy ? null : () => run(prepare), child: Text(tr('Preview and approve'))),
        OutlinedButton(onPressed: _busy ? null : () => run(delivery.sendPending), child: Text(tr('Send approved report'))),
        TextButton(onPressed: () async {
          await delivery.revoke();
          if (mounted) setState(() => _notice = 'Pending approval revoked. Already delivered data cannot be recalled.');
        }, child: Text(tr('Revoke pending approval'))),
      ],
    )),
  );
}
