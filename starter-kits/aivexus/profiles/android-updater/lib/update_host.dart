import 'dart:async';
import 'package:flutter/material.dart';
import 'package:aivexus_original_updater/aivexus_original_updater.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Adapted from owner-approved RendezVous 0.2.8/0.2.9 OTA UI; original engine retained.
String updateError(UpdateState s) {
  final message = (s.errorMessage ?? s.diagnostics.lastException ?? '').toLowerCase();
  if (message.contains('signature') || message.contains('verification') || message.contains('not valid') || message.contains('versioncode') || message.contains('split apk')) {
    return 'La mise à jour a été bloquée pour votre sécurité. Réessayez ou contactez l’assistance.';
  }
  if (s.diagnostics.canRequestPackageInstalls == false && s.diagnostics.apkDownloaded) {
    return 'Android nécessite votre autorisation pour installer cette mise à jour.';
  }
  if (message.contains('download')) return 'Téléchargement interrompu. Vérifiez votre connexion et réessayez.';
  if (message.contains('installer')) return 'Impossible de lancer l’installation. Réessayez.';
  return 'La mise à jour n’a pas pu être vérifiée ou installée. Vérifiez votre connexion et réessayez.';
}

class UpdateNoticePolicy {
  UpdateNoticePolicy({this.preferences});
  final SharedPreferences? preferences;
  final Set<String> _seen = {};
  final Set<String> _readySeen = {};
  static const _deferredKey = 'aivexus_deferred_update_install_path';
  String? readyKey(UpdateState s) {
    if (s.status != UpdateStatus.readyToInstall || !s.diagnostics.apkDownloaded || !s.diagnostics.apkFileExists) return null;
    final path = s.tempApkPath ?? s.diagnostics.apkPath;
    return path == null || path.isEmpty ? null : path;
  }
  bool shouldPromptInstall(UpdateState s) {
    final key = readyKey(s);
    return key != null && !_readySeen.contains(key) && preferences?.getString(_deferredKey) != key;
  }
  void markInstallSeen(UpdateState s) {
    final key = readyKey(s);
    if (key != null) _readySeen.add(key);
  }
  Future<void> deferInstall(UpdateState s) async {
    final key = readyKey(s);
    if (key != null) {
      _readySeen.add(key);
      await preferences?.setString(_deferredKey, key);
    }
  }
  String? availableKey(UpdateState s) {
    if (!s.hasUpdate || s.usedCachedManifest || s.latestManifest == null) return null;
    return '${s.preferredChannel.name}:${s.latestManifest!.version}:${s.latestManifest!.versionCode ?? ""}';
  }
  bool shouldPrompt(UpdateState s) {
    final key=availableKey(s);
    return key!=null && !_seen.contains(key);
  }
  void markSeen(UpdateState s) {
    final key=availableKey(s);
    if(key!=null) _seen.add(key);
  }
}

class AivexusUpdateHost extends StatefulWidget {
  const AivexusUpdateHost({super.key, required this.manager, required this.preferences, required this.appName, required this.body, this.tester = false});
  final UpdateManager manager;
  final String appName;
  final Widget body;
  final bool tester;
  final SharedPreferences preferences;
  @override State<AivexusUpdateHost> createState() => _AivexusUpdateHostState();
}

class _AivexusUpdateHostState extends State<AivexusUpdateHost> with WidgetsBindingObserver {
  late final notices=UpdateNoticePolicy(preferences: widget.preferences);
  bool _pageOpen=false, _promptOpen=false, _scheduled=false, _foreground=true;
  String? _lastError;

  @override void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.manager.state.addListener(_stateChanged);
    unawaited(widget.manager.refreshDiagnostics());
    unawaited(widget.manager.startBackgroundChecks(interval: const Duration(minutes: 2)));
  }
  @override void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground=state==AppLifecycleState.resumed;
    if (_foreground) {
      unawaited(widget.manager.refreshDiagnostics());
      _stateChanged();
    }
  }
  @override void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.manager.state.removeListener(_stateChanged);
    widget.manager.stopBackgroundChecks(); super.dispose();
  }

  void _stateChanged() {
    if (_scheduled || !mounted) return;
    _scheduled=true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _scheduled=false;
      if(!mounted || !_foreground || _promptOpen || (!_pageOpen && ModalRoute.of(context)?.isCurrent!=true)) return;
      final s=widget.manager.state.value;
      if(notices.shouldPromptInstall(s)) {
        // The Android system installer is the only installation confirmation.
        // Persist the attempted prompt before opening it: cancellation or
        // backgrounding must not cause another automatic launch.
        notices.markInstallSeen(s);
        _promptOpen=true;
        try {
          await notices.deferInstall(s);
          if(mounted && _foreground && notices.readyKey(widget.manager.state.value)==notices.readyKey(s)) {
            final ok=await installReadyUpdate(context,widget.manager);
            if(!ok&&mounted&&widget.manager.state.value.status==UpdateStatus.error&&!_pageOpen) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(updateError(widget.manager.state.value))));
            }
          }
        } finally { _promptOpen=false; }
        return;
      }
      if(_pageOpen) return;
      if(s.status==UpdateStatus.error) {
        final error=updateError(s);
        if(_lastError!=error) {
          _lastError=error;
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(error),action:SnackBarAction(label:'Détails',onPressed:(){unawaited(showUpdates());})));
        }
        return;
      }
      if(!notices.shouldPrompt(s)) return;
      notices.markSeen(s);
      _promptOpen=true;
      try {
        final accepted=await showDialog<bool>(context:context,builder:(ctx)=>AlertDialog(
          title:const Text('Nouvelle mise à jour'),
          content:Text('La version ${s.latestManifest!.version} est disponible. Voulez-vous la télécharger ?'),
          actions:[TextButton(onPressed:()=>Navigator.pop(ctx,false),child:const Text('Plus tard')),
            FilledButton(onPressed:()=>Navigator.pop(ctx,true),child:const Text('Télécharger'))]));
        if(accepted==true&&mounted) {
          _promptOpen=false;
          await showUpdates(approvedDownload:s);
        }
      } finally { _promptOpen=false; }
      if(mounted) _stateChanged();
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  Future<void> showUpdates({UpdateState? approvedDownload}) async {
    if(_pageOpen||!mounted) return;
    _pageOpen=true;
    notices.markSeen(widget.manager.state.value);
    try {
      await Navigator.of(context).push<void>(MaterialPageRoute(builder:(_)=>UpdatePanel(manager:widget.manager,notices:notices,approvedDownload:approvedDownload,tester:widget.tester)));
    } finally { _pageOpen=false; if(mounted) _stateChanged(); }
  }

  @override Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.appName), actions: [
      ValueListenableBuilder<UpdateState>(valueListenable: widget.manager.state,
        builder: (_, state, __) => IconButton(tooltip: 'Mises à jour', onPressed: showUpdates,
          icon: Icon(state.hasUpdate || state.status == UpdateStatus.readyToInstall ? Icons.system_update : state.status==UpdateStatus.error ? Icons.error_outline : Icons.update)))
    ]),
    body: widget.body);
}

class UpdatePanel extends StatefulWidget {
  const UpdatePanel({super.key, required this.manager, required this.notices, this.approvedDownload, this.tester = false});
  final bool tester;
  final UpdateManager manager;
  final UpdateNoticePolicy notices;
  final UpdateState? approvedDownload;
  @override State<UpdatePanel> createState()=>_UpdatePanelState();
}

class _UpdatePanelState extends State<UpdatePanel> with WidgetsBindingObserver {
  bool _actionBusy=false;
  String? _localError;
  UpdateManager get manager=>widget.manager;
  @override void initState(){
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(manager.refreshDiagnostics());
    final approved=widget.approvedDownload;
    if(approved!=null) WidgetsBinding.instance.addPostFrameCallback((_){
      if(mounted) unawaited(run(()=>download(approved)));
    });
  }
  @override void didChangeAppLifecycleState(AppLifecycleState state){
    if(state==AppLifecycleState.resumed) unawaited(manager.refreshDiagnostics());
  }
  @override void dispose(){WidgetsBinding.instance.removeObserver(this);super.dispose();}
  Future<void> run(Future<void> Function() action) async {
    if(_actionBusy)return;
    setState((){_actionBusy=true;_localError=null;});
    try{await action();}catch(_){if(mounted)setState(()=>_localError='Impossible de terminer cette opération. Réessayez.');}
    finally{if(mounted)setState(()=>_actionBusy=false);}
  }
  String label(UpdateStatus s)=>switch(s){
    UpdateStatus.idle=>'Prêt',
    UpdateStatus.checking=>'Recherche…',
    UpdateStatus.upToDate=>'Votre application est à jour',
    UpdateStatus.updateAvailable=>'Une mise à jour est disponible',
    UpdateStatus.downloading=>'Téléchargement…',
    UpdateStatus.readyToInstall=>'Mise à jour prête à installer',
    UpdateStatus.error=>'Mise à jour indisponible',
  };
  Future<void> download(UpdateState s) async {
    if(!mounted || manager.state.value.latestManifest?.version!=s.latestManifest?.version||!manager.state.value.hasUpdate||manager.state.value.usedCachedManifest)return;
    await manager.downloadLatestApk();
    await manager.refreshDiagnostics();
  }
  Future<void> install() async {
    await widget.notices.deferInstall(manager.state.value);
    if(!mounted)return;
    final ok=await installReadyUpdate(context,manager);
    if(!ok&&mounted&&manager.state.value.status!=UpdateStatus.error && manager.state.value.diagnostics.canRequestPackageInstalls!=false) {
      setState(()=>_localError='Impossible de lancer l’installation. Réessayez.');
    }
  }
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('Mises à jour')),
    body:ValueListenableBuilder<UpdateState>(valueListenable:manager.state,builder:(ctx,s,_){
      final busy=_actionBusy||s.status==UpdateStatus.checking||s.status==UpdateStatus.downloading;
      final ready=s.status==UpdateStatus.readyToInstall;
      return ListView(padding:const EdgeInsets.all(20),children:[
        Text('Version installée : ${s.currentVersion}',style:Theme.of(context).textTheme.titleMedium),
        if(s.latestManifest!=null) Text('Dernière version détectée : ${s.latestManifest!.version}'),
        const SizedBox(height:20),
        Text(label(s.status),style:Theme.of(context).textTheme.titleLarge),
        if(s.usedCachedManifest) const Text('Résultat précédent : connexion à vérifier avant le téléchargement.'),
        if(s.status==UpdateStatus.error) Text(updateError(s),style:TextStyle(color:Theme.of(context).colorScheme.error)),
        if(_localError!=null) Text(_localError!,style:TextStyle(color:Theme.of(context).colorScheme.error)),
        if(s.status==UpdateStatus.downloading)...[
          const SizedBox(height:12),
          LinearProgressIndicator(value:s.downloadProgress.clamp(0.0,1.0).toDouble()),
          Text('${(s.downloadProgress.clamp(0.0,1.0)*100).round()} %'),
        ],
        const SizedBox(height:24),
        if(s.hasUpdate&&!s.usedCachedManifest) FilledButton(onPressed:busy?null:()=>run(()=>download(s)),child:const Text('Télécharger')),
        if(ready) FilledButton(onPressed:busy?null:()=>run(install),child:const Text('Mettre à jour')),
        OutlinedButton(onPressed:busy||ready?null:()=>run(()async{await manager.checkForUpdates(allowCachedFallback:false);await manager.refreshDiagnostics();}),child:const Text('Rechercher une mise à jour')),
        if(widget.tester) ...[
        const SizedBox(height:24),
        const Text('Canal de mise à jour'),
        DropdownButton<ReleaseChannel>(value:s.preferredChannel,isExpanded:true,
          items:[for(final c in ReleaseChannel.values) DropdownMenuItem(value:c,child:Text(c.name))],
          onChanged:busy||ready?null:(c){if(c!=null)unawaited(run(()=>manager.setPreferredChannel(c)));}),
        ],
      ]);
    }));
}

Future<bool> installReadyUpdate(BuildContext context, UpdateManager manager) async {
  await manager.refreshDiagnostics();
  if(!context.mounted || manager.state.value.status!=UpdateStatus.readyToInstall) return false;
  if(manager.state.value.diagnostics.canRequestPackageInstalls==false){
    final accepted=await showDialog<bool>(context:context,builder:(ctx)=>AlertDialog(
      title:const Text('Autorisation Android nécessaire'),
      content:const Text('Autorisez cette application à installer ses mises à jour, puis confirmez l’installation.'),
      actions:[TextButton(onPressed:()=>Navigator.pop(ctx,false),child:const Text('Annuler')),FilledButton(onPressed:()=>Navigator.pop(ctx,true),child:const Text('Ouvrir les paramètres'))]));
    if(accepted==true&&context.mounted){
      final ok=await manager.openUnknownAppsSettings();
      if(!ok&&context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Impossible d’ouvrir les paramètres Android.')));
    }
    return false;
  }
  return manager.prepareInstallIntent();
}
