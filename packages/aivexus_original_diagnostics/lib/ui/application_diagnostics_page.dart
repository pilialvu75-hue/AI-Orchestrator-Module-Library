import 'package:flutter/material.dart';
import '../src/application_diagnostics.dart';
import '../src/exit_history.dart';
import '../src/diagnostic_labels.dart';

class ApplicationDiagnosticsPage extends StatefulWidget {
  const ApplicationDiagnosticsPage({super.key});
  @override
  State<ApplicationDiagnosticsPage> createState() => _ApplicationDiagnosticsPageState();
}
class _ApplicationDiagnosticsPageState extends State<ApplicationDiagnosticsPage> {
  final history = DiagnosticSession.instance.exitHistory;
  late final Future<DiagnosticAppInfo> info;
  @override
  void initState() {
    super.initState();
    info = DiagnosticAppInfo.read();
    history.refresh();
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(diagnosticLabel(context, 'Application information'))),
    body: ListView(children: [
      FutureBuilder<DiagnosticAppInfo>(future: info, builder: (_, snapshot) => Column(children: [
        ListTile(title: Text(diagnosticLabel(context, 'Version')), trailing: Text(diagnosticLabel(context, snapshot.data?.version ?? 'Unavailable'))),
        ListTile(title: Text(diagnosticLabel(context, 'Build')), trailing: Text(diagnosticLabel(context, snapshot.data?.build ?? 'Unavailable'))),
        ListTile(title: Text(diagnosticLabel(context, 'Platform')), trailing: Text(diagnosticLabel(context, snapshot.data?.platform ?? 'Unavailable'))),
      ])),
      const Divider(),
      ListTile(title: Text(diagnosticLabel(context, 'Historical Android process exits')),
        subtitle: Text(diagnosticLabel(context, 'Previous system records, not evidence of a new crash.'))),
      ListenableBuilder(listenable: history, builder: (_, __) => Column(children: [
        if (history.status == ExitHistoryStatus.loading) const LinearProgressIndicator(),
        if (history.status == ExitHistoryStatus.unavailable) ListTile(title: Text(diagnosticLabel(context, 'Unavailable'))),
        if (history.status == ExitHistoryStatus.available && history.records.isEmpty) ListTile(title: Text(diagnosticLabel(context, 'No retained exit records'))),
        for (final r in history.records) ListTile(title: Text(diagnosticLabel(context, r.reason.name)), subtitle: Text(r.timestamp.toLocal().toString())),
      ])),
      TextButton(onPressed: history.refresh, child: Text(diagnosticLabel(context, 'Refresh history'))),
    ]),
  );
}
