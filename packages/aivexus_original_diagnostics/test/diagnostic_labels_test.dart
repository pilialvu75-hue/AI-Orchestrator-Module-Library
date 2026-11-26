import 'package:flutter_test/flutter_test.dart';
import 'package:aivexus_original_diagnostics/src/diagnostic_labels.dart';

void main() {
  test('four language labels and English fallback', () {
    expect(diagnosticLabelFor('it', 'Resources'), 'Risorse');
    expect(diagnosticLabelFor('fr', 'Resources'), 'Ressources');
    expect(diagnosticLabelFor('es', 'Resources'), 'Recursos');
    expect(diagnosticLabelFor('en', 'Resources'), 'Resources');
    expect(diagnosticLabelFor('de', 'Resources'), 'Resources');
  });
}
