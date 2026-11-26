import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'updater_localizations.dart';
import 'package:aivexus_original_updater/core/system/update/release_channel.dart';
import 'package:aivexus_original_updater/core/system/update/update_manager.dart';
import 'package:aivexus_original_updater/core/system/update/update_state.dart';

class UpdateSettingsPage extends StatefulWidget {
  const UpdateSettingsPage({
    super.key,
    required this.updateManager,
  });

  final UpdateManager updateManager;

  @override
  State<UpdateSettingsPage> createState() => _UpdateSettingsPageState();
}

class _UpdateSettingsPageState extends State<UpdateSettingsPage> {
  late final UpdateManager _updateManager;
  static final DateFormat _lastCheckFormat = DateFormat.yMd().add_jm();
  bool _showDiagnostics = false;
  int _diagnosticsTapCount = 0;

  @override
  void initState() {
    super.initState();
    _updateManager = widget.updateManager;
    unawaited(_updateManager.refreshDiagnostics());
  }

  Future<void> _checkNow() async {
    await _updateManager.checkForUpdates();
    unawaited(_updateManager.refreshDiagnostics());
    if (!mounted) return;
    final l10n = context.l10n;
    final state = _updateManager.state.value;
    final message = switch (state.status) {
      UpdateStatus.updateAvailable => '${l10n.t('new_version_available')}: ${state.latestManifest?.version ?? '-'}',
      UpdateStatus.upToDate => l10n.t('already_up_to_date'),
      UpdateStatus.error => state.errorMessage ?? 'Update check failed',
      _ => l10n.t('update_check_completed'),
    };
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _downloadAndInstall() async {
    final ok = await _updateManager.downloadLatestApk();
    if (!ok || !mounted ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) return;
    await _updateManager.prepareInstallIntent();
    unawaited(_updateManager.refreshDiagnostics());
  }

  Future<void> _forceUpdate() async {
    final ok = await _updateManager.forceUpdate();
    unawaited(_updateManager.refreshDiagnostics());
    if (!mounted) return;
    final state = _updateManager.state.value;
    final message = ok
        ? context.l10n.t('force_update_started')
        : (state.errorMessage ?? context.l10n.t('force_update_failed'));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _installReady() async {
    await _updateManager.prepareInstallIntent();
    unawaited(_updateManager.refreshDiagnostics());
  }

  void _unlockDiagnostics() {
    _diagnosticsTapCount += 1;
    if (_diagnosticsTapCount >= 5 && !_showDiagnostics) {
      setState(() => _showDiagnostics = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Update diagnostics unlocked')),
      );
    }
  }

  Future<void> _openUnknownAppsSettings() async {
    final ok = await _updateManager.openUnknownAppsSettings();
    if (!mounted) return;
    final message = ok
        ? 'Opened Android install permission settings'
        : 'Failed to open install permission settings';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    unawaited(_updateManager.refreshDiagnostics());
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0D0D0D),
          elevation: 0,
          iconTheme: const IconThemeData(color: Colors.white),
        title: GestureDetector(
          onTap: _unlockDiagnostics,
          child: Text(
            l10n.t('updates'),
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
          ),
        ),
      ),
      body: ValueListenableBuilder<UpdateState>(
        valueListenable: _updateManager.state,
        builder: (context, state, _) {
          final canForceUpdate = _updateManager.hasDetectedNewerVersion(state);
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 24),
            children: [
              if (Platform.isAndroid) const Padding(
                padding: EdgeInsets.only(bottom: 16),
                child: Text(
                  'Dopo aver avviato il download puoi uscire dall’app o spegnere '
                  'lo schermo. Segui l’avanzamento nella notifica Android. '
                  'Riapri l’app per verificare e installare l’aggiornamento.',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
              Text(
                l10n.t('preferred_release_channel'),
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: ReleaseChannel.values.map((channel) {
                  return ChoiceChip(
                    label: Text(channel.name),
                    selected: state.preferredChannel == channel,
                    onSelected: (_) => _updateManager.setPreferredChannel(channel),
                    selectedColor: const Color(0xFF8AB4F8).withValues(alpha: 0.25),
                    labelStyle: TextStyle(
                      color: state.preferredChannel == channel
                          ? const Color(0xFF8AB4F8)
                          : Colors.white70,
                    ),
                    backgroundColor: const Color(0xFF1F1F1F),
                    side: BorderSide(
                      color: state.preferredChannel == channel
                          ? const Color(0xFF8AB4F8)
                          : Colors.white24,
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 28),
              // ── Version info ──────────────────────────────────────────────
              _InfoRow(
                label: l10n.t('current_version'),
                value: state.currentVersion,
                valueColor: Colors.white,
              ),
              const SizedBox(height: 8),
              _InfoRow(
                label: l10n.t('latest_known'),
                value: state.latestManifest != null
                    ? state.latestManifest!.version
                    : '–',
                valueColor: state.status == UpdateStatus.updateAvailable
                    ? const Color(0xFF69F0AE)
                    : Colors.white70,
              ),
              if (state.lastCheckedAt != null) ...[
                const SizedBox(height: 8),
                _InfoRow(
                  label: l10n.t('last_checked'),
                  value: _lastCheckFormat.format(state.lastCheckedAt!.toLocal()),
                  valueColor: Colors.white54,
                  small: true,
                ),
              ],
              if (state.usedCachedManifest) ...[
                const SizedBox(height: 6),
                const Text(
                  '⚠ Using cached update metadata (offline fallback).',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
              ],
              if (state.errorMessage != null) ...[
                const SizedBox(height: 8),
                Text(
                  state.errorMessage!,
                  style: const TextStyle(color: Color(0xFFFF8A80), fontSize: 12),
                ),
              ],
              const SizedBox(height: 24),
              // ── Status banner ─────────────────────────────────────────────
              if (state.status == UpdateStatus.updateAvailable) ...[
                _UpdateBanner(
                  version: state.latestManifest!.version,
                  changelog: state.latestManifest!.changelog,
                  critical: state.latestManifest!.critical,
                ),
                const SizedBox(height: 16),
              ],
              // ── Download progress ─────────────────────────────────────────
              if (state.status == UpdateStatus.downloading) ...[
                Row(
                  children: [
                    Expanded(
                      child: LinearProgressIndicator(
                        value: state.downloadProgress > 0
                            ? state.downloadProgress
                            : null,
                        backgroundColor: Colors.white12,
                        valueColor: const AlwaysStoppedAnimation<Color>(
                          Color(0xFF8AB4F8),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      '${(state.downloadProgress * 100).toStringAsFixed(0)}%',
                      style: const TextStyle(color: Colors.white70, fontSize: 12),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                const Text(
                  'Downloading update…',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 16),
              ],
              // ── Action buttons ────────────────────────────────────────────
              _ActionRow(
                state: state,
                canForceUpdate: canForceUpdate,
                onCheckNow: _checkNow,
                onDownloadAndInstall: _downloadAndInstall,
                onInstallReady: _installReady,
                onForceUpdate: _forceUpdate,
              ),
              if (_showDiagnostics) ...[
                const SizedBox(height: 22),
                _DiagnosticsCard(
                  state: state,
                  onRefresh: _updateManager.refreshDiagnostics,
                  onOpenUnknownAppsSettings: _openUnknownAppsSettings,
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

// ── Helper widgets ─────────────────────────────────────────────────────────────

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.label,
    required this.value,
    required this.valueColor,
    this.small = false,
  });

  final String label;
  final String value;
  final Color valueColor;
  final bool small;

  @override
  Widget build(BuildContext context) {
    final style = small
        ? const TextStyle(color: Colors.white54, fontSize: 12)
        : const TextStyle(color: Colors.white70);
    return Row(
      children: [
        Text('$label: ', style: style),
        Text(value, style: style.copyWith(color: valueColor, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _UpdateBanner extends StatelessWidget {
  const _UpdateBanner({
    required this.version,
    required this.changelog,
    required this.critical,
  });

  final String version;
  final String changelog;
  final bool critical;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: critical
            ? const Color(0xFFFF8A80).withValues(alpha: 0.12)
            : const Color(0xFF69F0AE).withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: critical ? const Color(0xFFFF8A80) : const Color(0xFF69F0AE),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                critical ? Icons.priority_high_rounded : Icons.system_update_alt_rounded,
                color: critical ? const Color(0xFFFF8A80) : const Color(0xFF69F0AE),
                size: 18,
              ),
              const SizedBox(width: 8),
              Text(
                critical ? 'Critical update — $version' : 'Update available — $version',
                style: TextStyle(
                  color: critical ? const Color(0xFFFF8A80) : const Color(0xFF69F0AE),
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ],
          ),
          if (changelog.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              changelog,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.state,
    required this.canForceUpdate,
    required this.onCheckNow,
    required this.onDownloadAndInstall,
    required this.onInstallReady,
    required this.onForceUpdate,
  });

  final UpdateState state;
  final bool canForceUpdate;
  final VoidCallback onCheckNow;
  final VoidCallback onDownloadAndInstall;
  final VoidCallback onInstallReady;
  final VoidCallback onForceUpdate;

  @override
  Widget build(BuildContext context) {
    final isChecking = state.status == UpdateStatus.checking;
    final isDownloading = state.status == UpdateStatus.downloading;
    final hasUpdate = state.status == UpdateStatus.updateAvailable;
    final readyToInstall = state.status == UpdateStatus.readyToInstall;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Wrap(
          alignment: WrapAlignment.end,
          spacing: 10,
          runSpacing: 10,
          children: [
            if (readyToInstall)
              FilledButton.icon(
                onPressed: onInstallReady,
                icon: const Icon(Icons.install_mobile_rounded),
                label: const Text('Install now'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF69F0AE),
                  foregroundColor: Colors.black,
                ),
              )
            else if (hasUpdate)
              FilledButton.icon(
                onPressed: isDownloading ? null : onDownloadAndInstall,
                icon: const Icon(Icons.download_rounded),
                label: const Text('Download & install'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF8AB4F8),
                  foregroundColor: Colors.black,
                ),
              ),
            FilledButton.icon(
              onPressed: (isChecking || isDownloading) ? null : onCheckNow,
              icon: const Icon(Icons.refresh),
              label: Text(
                isChecking
                    ? '${context.l10n.t('check_updates_now')}…'
                    : context.l10n.t('check_updates_now'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        FilledButton.icon(
          onPressed: (isChecking || isDownloading || !canForceUpdate)
              ? null
              : onForceUpdate,
          icon: const Icon(Icons.system_update_alt_rounded),
          label: Text(context.l10n.t('force_update')),
        ),
      ],
    );
  }
}

class _DiagnosticsCard extends StatelessWidget {
  const _DiagnosticsCard({
    required this.state,
    required this.onRefresh,
    required this.onOpenUnknownAppsSettings,
  });

  final UpdateState state;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onOpenUnknownAppsSettings;

  @override
  Widget build(BuildContext context) {
    final diagnostics = state.diagnostics;
    final canInstall = diagnostics.canRequestPackageInstalls;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Diagnostics',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 10),
          _InfoRow(
            label: 'Current installed version',
            value: state.currentVersion,
            valueColor: Colors.white,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Remote version',
            value: diagnostics.remoteVersion ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Remote versionCode',
            value: diagnostics.remoteVersionCode?.toString() ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Update URL',
            value: diagnostics.updateUrl ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'APK downloaded',
            value: diagnostics.apkDownloaded ? 'yes' : 'no',
            valueColor: diagnostics.apkDownloaded
                ? const Color(0xFF69F0AE)
                : Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'APK file path',
            value: diagnostics.apkPath ?? state.tempApkPath ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'APK file exists',
            value: diagnostics.apkFileExists ? 'yes' : 'no',
            valueColor: diagnostics.apkFileExists
                ? const Color(0xFF69F0AE)
                : Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Installer launch success',
            value: diagnostics.installerLaunchSuccess == null
                ? 'unknown'
                : (diagnostics.installerLaunchSuccess! ? 'success' : 'failure'),
            valueColor: diagnostics.installerLaunchSuccess == true
                ? const Color(0xFF69F0AE)
                : (diagnostics.installerLaunchSuccess == false
                    ? const Color(0xFFFF8A80)
                    : Colors.white70),
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Last installer result code',
            value: diagnostics.lastInstallerResultCode?.toString() ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Last exception',
            value: diagnostics.lastException ?? '–',
            valueColor: diagnostics.lastException == null
                ? Colors.white70
                : const Color(0xFFFF8A80),
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Android SDK version',
            value: diagnostics.androidSdkInt?.toString() ?? '–',
            valueColor: Colors.white70,
            small: true,
          ),
          const SizedBox(height: 6),
          _InfoRow(
            label: 'Unknown apps permission',
            value: canInstall == null ? 'unknown' : (canInstall ? 'granted' : 'denied'),
            valueColor: canInstall == true
                ? const Color(0xFF69F0AE)
                : (canInstall == false
                    ? const Color(0xFFFF8A80)
                    : Colors.white70),
            small: true,
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: () => unawaited(onRefresh()),
                icon: const Icon(Icons.bug_report_outlined),
                label: const Text('Refresh diagnostics'),
              ),
              if (canInstall == false)
                OutlinedButton.icon(
                  onPressed: () => unawaited(onOpenUnknownAppsSettings()),
                  icon: const Icon(Icons.settings_applications_outlined),
                  label: const Text('Grant install permission'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

