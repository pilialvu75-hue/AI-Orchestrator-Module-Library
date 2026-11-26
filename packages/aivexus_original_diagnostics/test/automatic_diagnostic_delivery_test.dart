import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

void main() {
  final target=DiagnosticRelayTarget(endpoint:Uri.parse('https://receiver.example.test/v1/rendezvous/0.2.12/report'),
    producer:'rendezvous',version:'0.2.12',platform:'android');
  final key=List.filled(64,'a').join();
  String event(DateTime timestamp,String event) =>
    '[${timestamp.toIso8601String()}] [AIVEXUS_DIAGNOSTIC] [AIVEXUS_DIAGNOSTIC] component=runtime event=$event';
  String receipt(DiagnosticReport report) {
    final hash=target.digest(report);
    return jsonEncode({'status':'verified','release':'diagnostics-rendezvous-v1-0.2.12',
      'asset':'rendezvous-diag-$hash.json','sha256':hash});
  }
  test('consent excludes historical events, failure survives restart, verified receipt advances cursor',() async {
    final dir=await Directory.systemTemp.createTemp('automatic-diag-');
    addTearDown(()=>dir.delete(recursive:true));
    final queue=File('${dir.path}/state.json');
    var now=DateTime.utc(2026,11,26,10,20);
    var history=event(now.subtract(const Duration(minutes:1)),'crash');
    var requests=0;
    String? body;
    http.Client factory()=>MockClient((request) async {
      requests++;
      expect(request.url,target.endpoint);
      expect(request.followRedirects,false);
      expect(request.headers.entries.firstWhere((e)=>e.key.toLowerCase()=='authorization').value,'Bearer $key');
      final report=DiagnosticReport.decode(request.body);
      expect(report.events,hasLength(1));
      expect(report.events.single['event'],'failed');
      if(requests==1) {body=request.body;throw const SocketException('offline');}
      expect(request.body,body);
      return http.Response(receipt(report),200);
    });
    AutomaticDiagnosticDelivery create()=>AutomaticDiagnosticDelivery(target:target,stateFile:queue,
      readCredential:() async=>key,readHistory:() async=>history,clock:()=>now,clientFactory:factory);
    final first=create();
    first.start(observeLifecycle:false);
    await first.tick();
    expect(requests,0);
    expect(first.grant(informedConsent:false),false);
    expect(first.grant(informedConsent:true),true);
    now=now.add(const Duration(seconds:1));
    history=event(now.subtract(const Duration(minutes:1)),'crash')+'\n'+event(now,'failed');
    await first.tick();
    expect(first.status,AutomaticDeliveryStatus.retryLater);
    expect(first.hasPending,true);
    expect(queue.readAsStringSync(),isNot(contains(key)));
    first.dispose();
    final restarted=create();
    addTearDown(restarted.dispose);
    restarted.start(observeLifecycle:false);
    expect(restarted.enabled,true);
    await restarted.tick();
    expect(requests,1);
    now=now.add(const Duration(minutes:1));
    await restarted.tick();
    expect(requests,2);
    expect(restarted.status,AutomaticDeliveryStatus.verified);
    expect(restarted.verifiedDigest,isNotNull);
    expect(restarted.hasPending,false);
    now=now.add(const Duration(minutes:6));
    await restarted.tick();
    expect(requests,2);
    expect(restarted.revoke(),true);
    expect(queue.existsSync(),false);
    history+='\n'+event(now,'timeout');
    await restarted.tick();
    expect(requests,2);
  });
  test('HTTP success without exact digest is not a receipt',() async {
    final dir=await Directory.systemTemp.createTemp('automatic-receipt-');
    addTearDown(()=>dir.delete(recursive:true));
    final queue=File('${dir.path}/state.json');
    var now=DateTime.utc(2026,11,26,10,20);
    var history='';
    final delivery=AutomaticDiagnosticDelivery(target:target,stateFile:queue,
      readCredential:() async=>key,readHistory:() async=>history,clock:()=>now,
      clientFactory:()=>MockClient((_) async=>http.Response('{"status":"verified"}',200)));
    addTearDown(delivery.dispose);
    delivery.start(observeLifecycle:false);
    delivery.grant(informedConsent:true);
    now=now.add(const Duration(seconds:1));
    history=event(now,'timeout');
    await delivery.tick();
    expect(delivery.hasPending,true);
    expect(delivery.verifiedDigest,isNull);
    expect(delivery.status,AutomaticDeliveryStatus.retryLater);
  });
  test('target change and missing credentials fail closed',() async {
    final dir=await Directory.systemTemp.createTemp('automatic-target-');
    addTearDown(()=>dir.delete(recursive:true));
    final queue=File('${dir.path}/state.json');
    var now=DateTime.utc(2026,11,26,10,20);
    var history='';
    var requests=0;
    final first=AutomaticDiagnosticDelivery(target:target,stateFile:queue,
      readCredential:() async=>null,readHistory:() async=>history,clock:()=>now,
      clientFactory:()=>MockClient((_) async {requests++;return http.Response('',200);}));
    first.start(observeLifecycle:false);
    first.grant(informedConsent:true);
    now=now.add(const Duration(seconds:1));
    history=event(now,'failed');
    await first.tick();
    expect(first.hasPending,true);
    expect(requests,0);
    first.dispose();
    final other=DiagnosticRelayTarget(endpoint:Uri.parse('https://other.example.test/v1/rendezvous/0.2.12/report'),
      producer:'rendezvous',version:'0.2.12',platform:'android');
    final restarted=AutomaticDiagnosticDelivery(target:other,stateFile:queue,
      readCredential:() async=>key,clock:()=>now);
    addTearDown(restarted.dispose);
    restarted.start(observeLifecycle:false);
    expect(restarted.enabled,false);
    expect(restarted.status,AutomaticDeliveryStatus.unavailable);
    expect(restarted.grant(informedConsent:true),false);
    expect(restarted.revoke(),true);
  });
}
