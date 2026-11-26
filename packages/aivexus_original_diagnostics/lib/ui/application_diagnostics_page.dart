import 'package:flutter/material.dart';
import '../src/application_diagnostics.dart';
import '../src/exit_history.dart';

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
    appBar: AppBar(title: const Text('Application information')),
    body: ListView(children: [
      FutureBuilder<DiagnosticAppInfo>(future: info, builder: (_, snapshot) => Column(children: [
        ListTile(title: const Text('Version'), trailing: Text(snapshot.data?.version ?? 'Unavailable')),
        ListTile(title: const Text('Build'), trailing: Text(snapshot.data?.build ?? 'Unavailable')),
        ListTile(title: const Text('Platform'), trailing: Text(snapshot.data?.platform ?? 'Unavailable')),
      ])),
      const Divider(),
      const ListTile(title: Text('Historical Android process exits'),
        subtitle: Text('Previous system records, not evidence of a new crash.')),
      ListenableBuilder(listenable: history, builder: (_, __) => Column(children: [
        if (history.status == ExitHistoryStatus.loading) const LinearProgressIndicator(),
        if (history.status == ExitHistoryStatus.unavailable) const ListTile(title: Text('Unavailable')),
        if (history.status == ExitHistoryStatus.available && history.records.isEmpty) const ListTile(title: Text('No retained exit records')),
        for (final r in history.records) ListTile(title: Text(r.reason.name), subtitle: Text(r.timestamp.toLocal().toString())),
      ])),
      TextButton(onPressed: history.refresh, child: const Text('Refresh history')),
    ]),
  );
}
