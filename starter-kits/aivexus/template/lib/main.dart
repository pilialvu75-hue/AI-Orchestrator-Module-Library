import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

const appName = __DISPLAY_NAME_DART__;

void main() => runApp(const AivexusApp());

class AivexusApp extends StatelessWidget {
  const AivexusApp({super.key, this.locale});
  final Locale? locale;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: appName,
      locale: locale,
      supportedLocales: const [
        Locale('it'), Locale('fr'), Locale('en'), Locale('es'),
      ],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      themeMode: ThemeMode.system,
      theme: ThemeData(colorSchemeSeed: const Color(0xff125566)),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xff125566),
      ),
      home: const AppHome(),
    );
  }
}

class AppHome extends StatelessWidget {
  const AppHome({super.key});

  static const labels = <String, String>{
    'it': 'Applicazione pronta',
    'fr': 'Application prête',
    'en': 'Application ready',
    'es': 'Aplicación lista',
  };

  @override
  Widget build(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    return Scaffold(
      appBar: AppBar(title: const Text(appName)),
      body: Center(child: Text(labels[language] ?? labels['en']!)),
    );
  }
}
