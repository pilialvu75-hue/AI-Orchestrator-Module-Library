import 'package:flutter/material.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await DiagnosticSession.instance.start();
  runApp(const SmokeApp());
}

class SmokeApp extends StatelessWidget {
  const SmokeApp({super.key});
  @override
  Widget build(BuildContext context) => const MaterialApp(
    title: 'AIVEXUS Diagnostics QA',
    home: SmokeHome(),
  );
}

class SmokeHome extends StatefulWidget {
  const SmokeHome({super.key});
  @override
  State<SmokeHome> createState() => _SmokeHomeState();
}

class _SmokeHomeState extends State<SmokeHome> {
  int count = 0;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('AIVEXUS Diagnostics QA')),
    body: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Text('Isolated test application. No network receiver.'),
      const SizedBox(height: 12),
      FilledButton(onPressed: () {
        AivexusDiagnostics.instance.record(
          DiagnosticComponent.runtime, DiagnosticEvent.failed, elapsedMs: 42);
        setState(() => count++);
      }, child: const Text('Record synthetic test failure')),
      Text('Synthetic events this run: $count'),
      const SizedBox(height: 24),
      const HiddenDiagnosticsEntry(child: Padding(
        padding: EdgeInsets.all(16), child: Text('QA 0.1.0'))),
    ])),
  );
}
