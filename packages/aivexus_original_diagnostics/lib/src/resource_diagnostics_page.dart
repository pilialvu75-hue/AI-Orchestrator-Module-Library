import 'package:flutter/material.dart';
import 'resource_diagnostics.dart';
import 'diagnostic_labels.dart';

/// Read-only local readings. Foreground-only, stops on lifecycle change and
/// disposal; never sums native heap and process RSS.
class ResourceDiagnosticsPage extends StatefulWidget {
  const ResourceDiagnosticsPage({super.key});
  @override
  State<ResourceDiagnosticsPage> createState() => _ResourceDiagnosticsPageState();
}

class _ResourceDiagnosticsPageState extends State<ResourceDiagnosticsPage> with WidgetsBindingObserver {
  final _monitor = ResourceDiagnostics();
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _monitor.startVisibleSampling();
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _monitor.startVisibleSampling();
    } else {
      _monitor.stopVisibleSampling();
    }
  }
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _monitor.dispose();
    super.dispose();
  }
  String mb(int? value) => value == null ? diagnosticLabel(context, 'Unavailable') : '${(value / 1048576).toStringAsFixed(1)} MiB';
  Widget line(String label, String value) => ListTile(title: Text(diagnosticLabel(context, label)), trailing: Text(diagnosticLabel(context, value)));
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(diagnosticLabel(context, 'Resources'))),
    body: ListenableBuilder(listenable: _monitor, builder: (_, __) {
      final s = _monitor.latest;
      return ListView(children: [
        line('Total RAM', mb(s?.totalBytes)),
        line('Available RAM', mb(s?.availableBytes)),
        line('Process RSS', mb(s?.rssBytes)),
        line('Native heap', mb(s?.nativeHeapBytes)),
        line('System CPU', s?.systemCpuPercent == null ? 'Unavailable' : '${s!.systemCpuPercent!.toStringAsFixed(1)}%'),
        line('Battery temperature', s?.batteryTemperatureC == null ? 'Unavailable' : '${s!.batteryTemperatureC!.toStringAsFixed(1)} °C'),
        line('Memory pressure', s?.pressure ?? 'Unknown'),
        line('Process CPU (one core = 100%)', s?.processCpuCorePercent == null ? 'Unavailable' : '${s!.processCpuCorePercent!.toStringAsFixed(1)}%'),
        line('GPU utilization', 'Unavailable'),
        line('App volume free space', mb(s?.appVolumeFreeBytes)),
        line('App volume total space', mb(s?.appVolumeTotalBytes)),
      ]);
    }),
  );
}
