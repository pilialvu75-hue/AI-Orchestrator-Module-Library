import 'package:flutter/widgets.dart';

// Extracted original translation keys, with original English fallback.
class UpdaterLocalizations {
  const UpdaterLocalizations(this.language);
  final String language;
  String t(String key) => _labels[language]?[key] ?? _labels['en']![key] ?? key;
  static const _labels = <String, Map<String, String>>{
    'en': {
      'updates': 'Updates',
      'preferred_release_channel': 'Preferred release channel',
      'check_updates_now': 'Check now',
      'force_update': 'Force update',
      'force_update_started': 'Force update started.',
      'force_update_failed': 'Force update could not start.',
      'latest_known': 'Latest known',
      'last_checked': 'Last checked',
      'already_up_to_date': 'Already up to date',
      'update_check_completed': 'Update check completed',
      'new_version_available': 'New version available',
      'current_version': 'Current version',
    },
    'fr': {
      'updates': 'Mises \u00e0 jour',
      'check_updates_now': 'V\u00e9rifier maintenant',
      'force_update': 'Forcer la mise \u00e0 jour',
      'force_update_started': 'Mise \u00e0 jour forc\u00e9e lanc\u00e9e.',
      'force_update_failed': 'La mise \u00e0 jour forc\u00e9e n\u2019a pas pu d\u00e9marrer.',
      'new_version_available': 'Nouvelle version disponible',
      'current_version': 'Version actuelle',
    },
    'it': {
      'updates': 'Aggiornamenti',
      'preferred_release_channel': 'Canale release preferito',
      'check_updates_now': 'Controlla ora',
      'force_update': 'Forza aggiornamento',
      'force_update_started': 'Aggiornamento forzato avviato.',
      'force_update_failed': 'Impossibile avviare l\u2019aggiornamento forzato.',
      'latest_known': 'Ultima rilevata',
      'last_checked': 'Ultimo controllo',
      'already_up_to_date': 'Già aggiornata',
      'update_check_completed': 'Controllo aggiornamenti completato',
      'new_version_available': 'Nuova versione disponibile',
      'current_version': 'Versione corrente',
    },
    'es': {
      'updates': 'Actualizaciones',
      'check_updates_now': 'Comprobar ahora',
      'force_update': 'Forzar actualizaci\u00f3n',
      'force_update_started': 'Actualizaci\u00f3n forzada iniciada.',
      'force_update_failed': 'No se pudo iniciar la actualizaci\u00f3n forzada.',
      'new_version_available': 'Nueva versi\u00f3n disponible',
      'current_version': 'Versi\u00f3n actual',
    },
    'de': {
      'updates': 'Updates',
      'check_updates_now': 'Jetzt pr\u00fcfen',
      'force_update': 'Update erzwingen',
      'force_update_started': 'Erzwungenes Update gestartet.',
      'force_update_failed': 'Erzwungenes Update konnte nicht gestartet werden.',
      'new_version_available': 'Neue Version verf\u00fcgbar',
      'current_version': 'Aktuelle Version',
    },
  };
}
extension UpdaterLocalizationContext on BuildContext {
  UpdaterLocalizations get l10n => UpdaterLocalizations(Localizations.localeOf(this).languageCode);
}
