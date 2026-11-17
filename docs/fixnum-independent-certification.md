# Primo modulo esterno: percorso di certificazione `fixnum`

**Stato iniziale:** `utility.int64_arithmetic.external.dartlang.fixnum@0.1.0`
è `TESTED` (consumer Dart/Linux reale), **non** `CERTIFIED`.
Il materiale storico e le scansioni automatiche sono richieste di revisione,
non approvazioni indipendenti.

## Catena operativa, senza autocertificazione

1. Il workflow `review-autonomous-public-dart.yml` produce un handoff
   `fixnum-independent-review-HANDOFF-BLOCKED.json`, SBOM, evidenza OSV
   e static-audit. Un revisore **indipendente dall'autore del candidato**
   controlla sorgente e adattatore esatti, licenza originale, inventario,
   eventuali advisory, privacy, chiamate di rete e prove del consumer.
2. Il revisore seleziona il **CycloneDX SBOM esatto** (file JSON non vuoto,
   con almeno un componente), verifica che sia accurato e documenta la
   decisione. Non dedurre "zero vulnerabilità" dall'assenza di dati.
3. Il revisore autorizzato, da ambiente protetto, firma un documento conforme
   a `ai-orchestrator.library-review-authorization.v1` con
   `tools/library_protected_review_sign.py`. La firma Ed25519 deve coprire
   `asset_id`, `version`, `source_commit`, `payload_sha256`,
   `sbom_sha256`, `license_file_sha256`, `reviewed_at`,
   `reviewer_id`, `known_vulnerabilities: 0` e
   `decision: APPROVED`. Usare solo valori verificati sulla copia immutable.
4. La **chiave privata** resta fuori dal repository, dalla PR e dai job che
   eseguono sorgente candidato. Il responsabile del repository configura
   una sola volta la **chiave pubblica autentica** in Actions variables:
   `LIBRARY_SECURITY_REVIEW_PUBLIC_KEY_PEM`. La stessa chiave viene
   usata dal già esistente workflow `certify-intake.yml`.
   Serve governance indipendente della chiave e protezione di `main`.
5. Soltanto dopo la revisione autentica, il responsabile crea una PR con
   questi due file (non includere mai la chiave privata):

   - `review-submissions/utility.int64_arithmetic.external.dartlang.fixnum/0.1.0/sbom.json`
   - `review-submissions/utility.int64_arithmetic.external.dartlang.fixnum/0.1.0/independent-attestation.json`

6. Dopo merge su `main`, `accept-signed-fixnum-review.yml` rilegge
   i byte reali, verifica la firma contro la chiave pubblica protetta,
   ricontrolla sorgente, licenza, SBOM, metadati e test, quindi esegue
   **promozione, esportazione e commit nello stesso job protetto**.
   Firme false, dati mancanti, hash discordanti o chiavi non configurate
   interrompono il job. Non si attende un secondo workflow `push`:
   GitHub non li avvia normalmente a seguito di un commit con `GITHUB_TOKEN`.
7. Il job senza permessi di scrittura di `prove-certified-consumer.yml`
   parte automaticamente con `workflow_run` al completamento riuscito della
   promozione e importa il pacchetto **certificato** in un consumer esterno.
   Una certificazione resta priva di prova d'uso finché questo consumer
   non ha completato l'esecuzione reale con esito positivo.

## Criteri di completamento

Non dichiarare `CERTIFIED` basandosi sul solo PASS di `validate`,
sulla firma prodotta da una chiave sintetica nei test, o su un documento
`REQUEST-NOT-CERTIFIED`. Sono necessarie **tutte** queste evidenze:
revisione esterna firmata e legata ai byte esatti, CI di certificazione PASS,
modulo in `modules/`, voce in `packages/index.json` ed esecuzione riuscita
di un consumer del pacchetto esportato.

L'integrazione iniziale è dimostrata su **Linux/Dart**; Windows, Android e
macOS devono disporre di collaudi propri prima di dichiarare supporto reale.
Il flusso successivo alla consegna dell'approvazione è automatico; una
autorizzazione indipendente non può essere inventata dal produttore.

## Evidenze tecniche firmate in autonomia (senza certificazione)

Il workflow `fixnum-keyless-technical-review.yml`, attivo su `main`,
a richiesta e giornalmente, ricostruisce l'intero handoff da sorgenti
materializzati: controlla la licenza originale identica alla copia vendor,
gli hash sorgente, l'inventario SBOM, il risultato di una nuova scansione
OSV, l'analisi statica e l'identità dell'esecuzione CI storica recuperata
direttamente dalle API GitHub. Il risultato è
`TECHNICAL_EVIDENCE_READY_PENDING_INDEPENDENT_REVIEW`, **mai**
`APPROVED` né `CERTIFIED`.

GitHub Actions usa `actions/attest@v4` per produrre una attestazione
Sigstore *delle prove tecniche* e verifica il bundle con
`gh attestation verify` contro l'identità **esatta** del workflow
`fixnum-keyless-technical-review.yml@refs/heads/main`. È un documento
crittograficamente autenticato riguardo a chi ha prodotto le prove;
**non** è una firma indipendente di security approval.

### Prerequisito operativo di governance

Alla verifica del 17 novembre 2026, `main` risulta **non protetto**
(`GET /repos/.../branches/main: protected=false`) e non sono state
trovate ruleset attive. Il workflow di accettazione firmata rifiuta ora
qualsiasi promozione in queste condizioni. Un amministratore deve
configurare in GitHub le regole di `main`: pull request obbligatorie,
approvazioni indipendenti e check CI richiesti, senza bypass per i
produttori del candidato. Prima di definire realmente autonoma la
certificazione, occorre anche stabilire se la policy di sicurezza
consenta una decisione automatica indipendente e come renderne
immutabile/controllabile l'identità. Non creare approvazioni
retroattive o chiavi fittizie per oltrepassare questo requisito.
