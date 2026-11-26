import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:http/http.dart' as http;
import 'diagnostic_report.dart';
import 'diagnostics.dart';

enum AutomaticDeliveryStatus { disabled, waiting, sending, verified, retryLater, blocked, unavailable }

/// Fixed owner-approved destination; never construct from log content.
class DiagnosticRelayTarget {
  DiagnosticRelayTarget({required this.endpoint, required this.producer,
    required this.version, required this.platform}) {
    if (!RegExp(r'^[a-z][a-z0-9-]{0,31}$').hasMatch(producer) ||
        !RegExp(r'^\d+\.\d+\.\d+$').hasMatch(version) ||
        !const {'android','windows','linux','macos','ios'}.contains(platform) ||
        endpoint.scheme != 'https' || endpoint.host.isEmpty ||
        endpoint.userInfo.isNotEmpty || endpoint.hasQuery || endpoint.hasFragment ||
        endpoint.port != 443 || endpoint.path != '/v1/$producer/$version/report') {
      throw ArgumentError('Invalid fixed diagnostics relay target');
    }
  }
  final Uri endpoint;
  final String producer, version, platform;

  String digest(DiagnosticReport report) {
    final archive=jsonEncode({'schema':'aivexus.diagnostics.report.v1',
      'producer':producer,'producer_version':version,'platform':platform,'events':report.events});
    return sha256.convert(utf8.encode(archive)).toString();
  }
  bool verifies(Object? receipt, DiagnosticReport report) {
    final hash=digest(report);
    return receipt is Map && receipt.length==4 &&
        receipt['status']=='verified' &&
        receipt['release']=='diagnostics-$producer-v1-$version' &&
        receipt['asset']=='$producer-diag-$hash.json' &&
        receipt['sha256']==hash;
  }
}

/// One private state file per target, one owner isolate. No GitHub token,
/// no credentials stored here, no uploads before explicit informed consent.
/// Automatically retries only while foregrounded; exact receipt is required.
class AutomaticDiagnosticDelivery extends ChangeNotifier with WidgetsBindingObserver {
  AutomaticDiagnosticDelivery({required this.target,required File stateFile,
    required Future<String?> Function() readCredential,
    Future<String> Function()? readHistory,http.Client Function()? clientFactory,
    DateTime Function()? clock})
      : _file=stateFile,_readCredential=readCredential,
        _readHistory=readHistory??AivexusDiagnostics.instance.readSafeHistory,
        _clientFactory=clientFactory??(()=>http.Client()),_clock=clock??DateTime.now;
  final DiagnosticRelayTarget target;
  final File _file;
  final Future<String?> Function() _readCredential;
  final Future<String> Function() _readHistory;
  final http.Client Function() _clientFactory;
  final DateTime Function() _clock;
  static const _delays=[1,5,15,60,180,360,720,1440];
  static const _maxAge=Duration(days:7);
  Map<String,dynamic>? _data;
  Timer? _timer;
  http.Client? _active;
  bool _enabled=false,_started=false,_observe=false,_foreground=true,_busy=false,_disposed=false;
  AutomaticDeliveryStatus _status=AutomaticDeliveryStatus.disabled;
  AutomaticDeliveryStatus get status=>_status;
  bool get enabled=>_enabled;
  bool get hasPending=>_data?['report']!=null;
  String? get verifiedDigest=>_data?['last_verified'] as String?;
  String get _identity=>'${target.endpoint}|${target.producer}|${target.version}|${target.platform}';
  DateTime get _now=>_clock().toUtc();
  String _utc(DateTime date)=>date.toUtc().toIso8601String();
  void _set(AutomaticDeliveryStatus value) {
    _status=value;
    if(!_disposed) notifyListeners();
  }

  void _save(Map<String,dynamic> d) {
    final encoded=jsonEncode(d);
    if(encoded.length>65536) throw const FormatException('Queue too large');
    _file.parent.createSync(recursive:true);
    final tmp=File('${_file.path}.tmp');
    try {
      tmp.writeAsStringSync(encoded,flush:true);
      tmp.renameSync(_file.path);
    } finally { if(tmp.existsSync()) tmp.deleteSync(); }
    _data=d;
  }
  Map<String,dynamic> _load() {
    if(_file.lengthSync()>65536) throw const FormatException('Queue too large');
    final d=jsonDecode(_file.readAsStringSync());
    if(d is! Map<String,dynamic> ||
        d.keys.any((k)=>!const {'target','consent','cursor','next','attempts','report','batch_end','last_verified','blocked'}.contains(k)) ||
        d['target']!=_identity || d['consent'] is! String || d['cursor'] is! String ||
        d['next'] is! String || d['attempts'] is! int ||
        (d['attempts'] as int)<0 || (d['attempts'] as int)>_delays.length ||
        (d['blocked']!=null && d['blocked']!=true)) throw const FormatException('Invalid state');
    final consent=DateTime.parse(d['consent'] as String).toUtc();
    final cursor=DateTime.parse(d['cursor'] as String).toUtc();
    DateTime.parse(d['next'] as String);
    if(consent.isAfter(_now)||cursor.isBefore(consent)||cursor.isAfter(_now)) throw const FormatException('Invalid consent time');
    if(d['report']!=null) {
      if(d['report'] is! String||d['batch_end'] is! String) throw const FormatException('Invalid batch');
      final report=DiagnosticReport.decode(d['report'] as String);
      final end=DateTime.parse(d['batch_end'] as String).toUtc();
      if(!end.isAfter(cursor)||end.isAfter(_now)) throw const FormatException('Invalid batch time');
      for(final event in report.events) {
        final time=DateTime.parse(event['time'] as String);
        if(time.isBefore(consent.subtract(const Duration(minutes:1)))||time.isAfter(end)) throw const FormatException('Invalid event time');
      }
    } else if(d['batch_end']!=null||d['attempts']!=0) {
      throw const FormatException('Invalid empty batch');
    }
    if(d['last_verified']!=null&&(d['last_verified'] is! String||
        !RegExp(r'^[a-f0-9]{64}$').hasMatch(d['last_verified'] as String))) throw const FormatException('Invalid receipt');
    return d;
  }
  /// observeLifecycle:false is for deterministic host-driven tests.
  void start({bool observeLifecycle=true}) {
    if(_started||_disposed) return;
    _started=true; _observe=observeLifecycle;
    if(_observe) {
      WidgetsBinding.instance.addObserver(this);
      _foreground=WidgetsBinding.instance.lifecycleState==null||
        WidgetsBinding.instance.lifecycleState==AppLifecycleState.resumed;
    }
    try {
      if(_file.existsSync()) {
        _data=_load(); _enabled=true;
        _set(_data?['blocked']==true?AutomaticDeliveryStatus.blocked:AutomaticDeliveryStatus.waiting);
      }
    } catch (_) { _enabled=false;_set(AutomaticDeliveryStatus.unavailable); }
    _schedule();
  }
  /// The host must disclose the public recipient, categories, automatic
  /// delivery, retention and revocation. No retroactive collection.
  bool grant({required bool informedConsent}) {
    if(!informedConsent||_disposed||_busy||_enabled||_file.existsSync()) return false;
    try {
      final now=_utc(_now);
      _save({'target':_identity,'consent':now,'cursor':now,'next':now,'attempts':0});
      _enabled=true;_set(AutomaticDeliveryStatus.waiting);_schedule();return true;
    } catch (_) { _set(AutomaticDeliveryStatus.unavailable);return false; }
  }
  bool revoke() {
    _enabled=false;_timer?.cancel();_timer=null;_active?.close();_data=null;
    try {
      if(_file.existsSync()) _file.deleteSync();
      final tmp=File('${_file.path}.tmp');
      if(tmp.existsSync()) tmp.deleteSync();
      _set(AutomaticDeliveryStatus.disabled);return true;
    } catch (_) { _set(AutomaticDeliveryStatus.unavailable);return false; }
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground=state==AppLifecycleState.resumed;
    _schedule();
  }
  void _schedule() {
    _timer?.cancel();_timer=null;
    if(!_started||!_observe||!_enabled||!_foreground||_disposed) return;
    _timer=Timer.periodic(const Duration(minutes:1),(_)=>unawaited(tick()));
    unawaited(tick());
  }
  Map<String,dynamic>? _newBatch(String history,Map<String,dynamic> d,DateTime now) {
    final cursor=DateTime.parse(d['cursor'] as String).toUtc();
    final candidates=<({DateTime time,String line})>[];
    final stamp=RegExp(r'^\[([^\]]+)\]');
    for(final line in history.split('\n')) {
      final m=stamp.firstMatch(line);
      final time=m==null?null:DateTime.tryParse(m[1]!)?.toUtc();
      if(time==null||!time.isAfter(cursor)||time.isAfter(now)||
          now.difference(time)>=_maxAge||
          DiagnosticReport.fromSafeHistory(line).events.isEmpty) continue;
      candidates.add((time:time,line:line));
    }
    candidates.sort((a,b)=>a.time.compareTo(b.time));
    final selected=candidates.take(DiagnosticReport.maxEvents).toList();
    if(selected.isEmpty) return null;
    final report=DiagnosticReport.fromSafeHistory(selected.map((e)=>e.line).join('\n'));
    return {...d,'report':report.json,'batch_end':_utc(selected.last.time),'attempts':0};
  }
  Future<String> _boundedResponse(http.StreamedResponse response) async {
    final bytes=<int>[];
    await for(final part in response.stream) {
      if(bytes.length+part.length>4096) throw const FormatException('Receipt too large');
      bytes.addAll(part);
    }
    return utf8.decode(bytes);
  }
  Future<void> tick() async {
    if(!_enabled||!_foreground||_busy||_disposed||_data==null) return;
    _busy=true;
    try {
      var d=Map<String,dynamic>.from(_data!);
      final now=_now;
      if(d['blocked']==true) { _set(AutomaticDeliveryStatus.blocked);return; }
      if(now.isBefore(DateTime.parse(d['next'] as String))) return;
      if(d['report']==null) {
        final history=await _readHistory();
        if(!_enabled||_disposed||!_foreground) return;
        final batch=_newBatch(history,d,now);
        if(batch==null) return;
        d=batch;_save(d);
      }
      final report=DiagnosticReport.decode(d['report'] as String);
      final oldest=DateTime.parse(report.events.first['time'] as String).toUtc();
      final attempt=d['attempts'] as int;
      if(attempt>=_delays.length||now.difference(oldest)>=_maxAge) {
        _save({...d,'blocked':true});_set(AutomaticDeliveryStatus.blocked);return;
      }
      final credential=await _readCredential();
      if(!_enabled||_disposed||!_foreground) return;
      if(credential==null||!RegExp(r'^[a-f0-9]{64}$').hasMatch(credential)) {
        _set(AutomaticDeliveryStatus.unavailable);return;
      }
      d={...d,'attempts':attempt+1,'next':_utc(now.add(Duration(minutes:_delays[attempt])))};
      _save(d);_set(AutomaticDeliveryStatus.sending);
      final client=_clientFactory();_active=client;
      try {
        final req=http.Request('POST',target.endpoint)
          ..followRedirects=false
          ..headers['Content-Type']='application/json'
          ..headers['Authorization']='Bearer $credential'
          ..body=report.json;
        final response=await client.send(req).timeout(const Duration(seconds:15));
        if(!_enabled||_disposed) return;
        if(response.statusCode==200) {
          final receipt=jsonDecode(await _boundedResponse(response).timeout(const Duration(seconds:10)));
          if(!_enabled||_disposed) return;
          if(!target.verifies(receipt,report)) throw const FormatException('Unverified receipt');
          _save({'target':_identity,'consent':d['consent'],'cursor':d['batch_end'],
            'next':_utc(_now.add(const Duration(minutes:5))),'attempts':0,'last_verified':target.digest(report)});
          _set(AutomaticDeliveryStatus.verified);
        } else if(response.statusCode==408||response.statusCode==429||
            response.statusCode>=500&&response.statusCode<=599) {
          _set(AutomaticDeliveryStatus.retryLater);
        } else {
          _save({...d,'blocked':true});_set(AutomaticDeliveryStatus.blocked);
        }
      } catch (_) {
        if(_enabled&&!_disposed) _set(AutomaticDeliveryStatus.retryLater);
      } finally { client.close();_active=null; }
    } catch (_) {
      if(_enabled&&!_disposed) _set(AutomaticDeliveryStatus.unavailable);
    } finally { _busy=false; }
  }
  @override
  void dispose() {
    _disposed=true;_timer?.cancel();_active?.close();
    if(_observe) WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}
