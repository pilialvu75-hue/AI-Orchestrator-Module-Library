import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:aivexus_original_updater/aivexus_original_updater.dart';
import 'package:aivexus_original_updater/core/config/app/app_constants.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'update_host.dart';

const appName = __DISPLAY_NAME_DART__;
const tester = __TESTER__;
const owner = '__GITHUB_OWNER__';
const repository = '__GITHUB_REPO__';
const manifest = 'https://raw.githubusercontent.com/$owner/$repository/main/update/version.json';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  if (!tester) {
    // New customer installs have their own package ID and stable feed.
    await prefs.setString(AppConstants.prefReleaseChannel, ReleaseChannel.stable.storageValue);
  }
  final info = await PackageInfo.fromPlatform();
  final client = http.Client();
  const comparator = VersionComparator();
  final checker = UpdateChecker(httpClient: client, preferences: prefs,
      comparator: comparator, manifestUrl: manifest, githubOwner: owner,
      githubRepo: repository, targetPlatform: UpdateTargetPlatform.android,
      manifestOnly: true, requireApkSha256: true);
  final manager = UpdateManager(updateChecker: checker, comparator: comparator,
      preferences: prefs, intentHandler: AndroidIntentHandler(),
      currentVersion: info.version, allowDebugSignatureMismatchBypass: false,
      requireApkSha256: true, enableAndroidBetaBuildNumberComparison: tester);
  runApp(StarterApp(manager: manager, client: client, preferences: prefs));
}

class StarterApp extends StatefulWidget {
  const StarterApp({super.key, required this.manager, required this.client, required this.preferences});
  final UpdateManager manager;
  final http.Client client;
  final SharedPreferences preferences;
  @override
  State<StarterApp> createState() => _StarterAppState();
}

class _StarterAppState extends State<StarterApp> {
  @override
  void dispose() {
    widget.manager.dispose();
    widget.client.close();
    super.dispose();
  }
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: appName,
    supportedLocales: const [Locale('it'), Locale('fr'), Locale('en'), Locale('es')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    themeMode: ThemeMode.system,
    theme: ThemeData(colorSchemeSeed: const Color(0xff125566)),
    darkTheme: ThemeData(brightness: Brightness.dark, colorSchemeSeed: const Color(0xff125566)),
    home: AivexusUpdateHost(manager: widget.manager, preferences: widget.preferences,
      appName: appName, tester: tester, body: const StarterBody()),
  );
}

class StarterBody extends StatelessWidget {
  const StarterBody({super.key});
  @override
  Widget build(BuildContext context) {
    const labels = {'it':'Applicazione pronta','fr':'Application prête','en':'Application ready','es':'Aplicación lista'};
    return Center(child: Text(labels[Localizations.localeOf(context).languageCode] ?? labels['en']!));
  }
}
