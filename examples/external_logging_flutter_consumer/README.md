# Prima app Flutter Android di prova per un modulo esterno reale

Questa è una **app separata da AI-Orchestrator**, con una semplice interfaccia
Flutter e tre pulsanti. La dipendenza nel `pubspec.yaml` punta al codice
fisicamente materializzato e testato della Libreria:

`intake/diagnostics.logging.dartlang.logging_adapter/0.1.1/payload/src`

- Origine esterna pubblica: `dart-lang/core`, `logging` 1.3.0,
  commit `8151b9f57fa3fee10421a19ce24470e143c0dee5`.
- Adattatore Aivexus: versione 0.1.1, eventi tipizzati e lista chiusa.
- Le azioni nell'app producono eventi reali nella memoria dell'app, poi
  visualizzati nella schermata; nessun inserimento di testo libero.
- Niente backend, permessi personali, credenziali, file degli utenti,
  caricamento di prompt, invio dei log, chiamate cloud o telemetria nel codice
  del modulo e della demo.

## Verifica e APK sperimentale
La workflow GitHub dedicata verifica l'SHA256 pin del modulo, genera solo sul
runner lo scheletro Android standard, esegue `flutter analyze`,
`flutter test` e compila un APK Android arm64 da consegnare come artifact.

Per riprodurre manualmente con Flutter SDK e Android SDK:
```sh
cd examples/external_logging_flutter_consumer
flutter create --empty --platforms=android --project-name=aivexus_external_logging_flutter_demo --org=ai.aivexus.demo .
flutter pub get
flutter test
flutter build apk --release --target-platform android-arm64
```

**Non è una release AI-Orchestrator**, e il successo di una build Android non
dimostra un test fisico sul Galaxy S24 FE. Il modulo è `tested`, non
`certified`: non è ancora autorizzato alla distribuzione produttiva o
integrato nell'app principale. La revisione indipendente della sicurezza,
della privacy e della licenza resta obbligatoria.
