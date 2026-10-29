import 'dart:async';

import 'package:aivexus_external_logging/aivexus_external_logging.dart';
import 'package:flutter/material.dart';

void main() => runApp(const ExternalLoggingDemoApp());

/// An isolated visual consumer; it never records raw prompts or user strings.
class ExternalLoggingDemoApp extends StatelessWidget {
  const ExternalLoggingDemoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Aivexus • Modulo esterno',
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: Colors.indigoAccent,
      ),
      home: const ExternalLoggingHome(),
    );
  }
}

class ExternalLoggingHome extends StatefulWidget {
  const ExternalLoggingHome({super.key});

  @override
  State<ExternalLoggingHome> createState() => _ExternalLoggingHomeState();
}

class _ExternalLoggingHomeState extends State<ExternalLoggingHome> {
  final AivexusLoggingModule _module = AivexusLoggingModule(capacity: 24);
  List<AivexusLogEntry> _entries = const [];

  void _emit(AivexusEventCode event, AivexusSeverity level) {
    _module.emit(event, severity: level);
    setState(() => _entries = _module.snapshot());
  }

  @override
  void dispose() {
    unawaited(_module.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Aivexus • Modulo esterno')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Dart logging 1.3.0',
                        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                    SizedBox(height: 6),
                    Text('Codice pubblico reale • adattatore Aivexus 0.1.1'),
                    SizedBox(height: 12),
                    Text('PROVA LOCALE — NON CERTIFICATO',
                        style: TextStyle(color: Colors.amberAccent)),
                    Text('Nessun prompt, campo libero o invio di eventi in rete.'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            const Text('Genera eventi tipizzati'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  key: const Key('emit-start'),
                  onPressed: () => _emit(
                      AivexusEventCode.startupReady, AivexusSeverity.info),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Avvio'),
                ),
                FilledButton.tonalIcon(
                  key: const Key('emit-model'),
                  onPressed: () => _emit(
                      AivexusEventCode.localModelLoaded, AivexusSeverity.debug),
                  icon: const Icon(Icons.memory),
                  label: const Text('Modello caricato'),
                ),
                OutlinedButton.icon(
                  key: const Key('emit-retry'),
                  onPressed: () => _emit(
                      AivexusEventCode.retryScheduled, AivexusSeverity.warning),
                  icon: const Icon(Icons.replay),
                  label: const Text('Riprova'),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Text('Eventi locali: ${_entries.length}',
                key: const Key('event-count'),
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_entries.isEmpty)
              const Text('Tocca un pulsante per provare il modulo.')
            else
              for (final event in _entries.reversed)
                Card(
                  key: ValueKey('event-${event.eventCode}-${event.timestampUtc.microsecondsSinceEpoch}'),
                  child: ListTile(
                    leading: const Icon(Icons.verified_outlined),
                    title: Text(event.eventCode),
                    subtitle: Text('Livello: ${event.severity.name}'),
                  ),
                ),
            const SizedBox(height: 16),
            const Text('Gli eventi restano soltanto in memoria. '
                'Questa app dimostrativa non installa il modulo in AI-Orchestrator.'),
          ],
        ),
      ),
    );
  }
}
