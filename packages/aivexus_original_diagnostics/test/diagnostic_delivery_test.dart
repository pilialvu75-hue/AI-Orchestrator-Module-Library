import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:aivexus_original_diagnostics/aivexus_original_diagnostics.dart';

void main() {
  const valid = '[2026-11-26T10:15:32.123Z] [AIVEXUS_DIAGNOSTIC] [AIVEXUS_DIAGNOSTIC] component=updater event=failed elapsed_ms=120';
  final endpoint = Uri.parse('https://diagnostics.example.test/v1/report');
  test('report is closed vocabulary, minute precision and rejects injected raw data', () {
    final report = DiagnosticReport.fromSafeHistory('$valid\n$valid path=/secret\n[SECRET] private text');
    expect(report.events, hasLength(1));
    expect(report.json, isNot(contains('secret')));
    expect(report.events.single['time'], '2026-11-26T10:15:00.000Z');
    expect(DiagnosticReport.decode(report.json).json, report.json);
    expect(() => DiagnosticReport.decode('{"schema":1,"events":[{"time":"2026-11-26T10:15:00.000Z","component":"updater","event":"failed","path":"secret"}]}'), throwsFormatException);
  });

  test('consent, bounded retry, restart and exact destination', () async {
    final dir = await Directory.systemTemp.createTemp('diag-delivery-');
    addTearDown(() => dir.delete(recursive:true));
    final queue = File('${dir.path}/queue.json');
    var now = DateTime.utc(2026,11,26,10,20);
    var requests = 0;
    String? key;
    http.Client factory() => MockClient((req) async {
      requests++;
      expect(req.url, endpoint);
      expect(req.followRedirects, false);
      expect(req.headers['authorization'], isNull);
      final currentKey = req.headers.entries.firstWhere((e) => e.key.toLowerCase() == 'idempotency-key').value;
      key ??= currentKey;
      expect(currentKey, key);
      expect(jsonDecode(req.body)['events'], hasLength(1));
      return http.Response('', requests == 1 ? 503 : 200);
    });
    final first = DiagnosticDelivery(endpoint:endpoint, queueFile:queue, clientFactory:factory, clock:()=>now);
    final report = DiagnosticReport.fromSafeHistory(valid);
    expect(await first.queueApproved(report, consent:false), false);
    await first.sendPending();
    expect(requests, 0);
    expect(await first.queueApproved(report, consent:true), true);
    expect(requests, 0);
    await first.sendPending();
    expect(first.state, DeliveryState.retryLater);
    expect(requests, 1);
    first.dispose();
    final second = DiagnosticDelivery(endpoint:endpoint, queueFile:queue, clientFactory:factory, clock:()=>now);
    addTearDown(second.dispose);
    await second.sendPending();
    expect(requests, 1);
    now = now.add(const Duration(minutes:1));
    await second.sendPending();
    expect(second.state, DeliveryState.sent);
    expect(requests, 2);
    expect(await queue.exists(), false);
  });

  test('revocation, expiration and destination change prevent transmission', () async {
    final dir = await Directory.systemTemp.createTemp('diag-revoke-');
    addTearDown(() => dir.delete(recursive:true));
    final queue = File('${dir.path}/queue.json');
    var now = DateTime.utc(2026,11,26,10,20);
    var requests = 0;
    http.Client factory() => MockClient((_) async { requests++; return http.Response('',200); });
    final delivery = DiagnosticDelivery(endpoint:endpoint, queueFile:queue, clientFactory:factory, clock:()=>now);
    addTearDown(delivery.dispose);
    final report = DiagnosticReport.fromSafeHistory(valid);
    expect(await delivery.queueApproved(report, consent:true), true);
    await delivery.revoke();
    await delivery.sendPending();
    expect(requests,0);
    expect(await queue.exists(),false);
    expect(await delivery.queueApproved(report, consent:true),true);
    final other = DiagnosticDelivery(endpoint:Uri.parse('https://other.example.test/report'),queueFile:queue,clientFactory:factory,clock:()=>now);
    await other.sendPending();
    expect(other.state,DeliveryState.rejected);
    other.dispose();
    expect(await delivery.queueApproved(report,consent:true),true);
    now = now.add(const Duration(hours:24));
    await delivery.sendPending();
    expect(delivery.state, DeliveryState.expired);
    expect(requests,0);
  });

  test('HTTP and embedded credentials rejected', () {
    for (final url in ['http://example.test/report','https://user:password@example.test/report','https://example.test/report?token=secret']) {
      expect(() => DiagnosticDelivery(endpoint:Uri.parse(url),queueFile:File('unused')),throwsArgumentError);
    }
  });
}
