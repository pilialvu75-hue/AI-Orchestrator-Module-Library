# Modulistica a due livelli: velocità di prova, certificazione separata

**Obiettivo:** un modulo realmente esistente, già testato, non deve restare
inutilizzabile solo perché non è ancora stato certificato per la distribuzione.
La politica della PR #170 impone una firma Ed25519 indipendente per **rilasciare
codice locale come certificato**; non deve bloccare i cicli autonomi di prova
in un Cantiere isolato.

## Livello A — Source preview, automatico

Un candidato `intake/*/*` da un repository posseduto da Aivexus può produrre automaticamente un pacchetto
`sandbox_preview` quando:

- è `tested`, con report di test presente, coerenza fra manifest, report,
  commit, piattaforme validate e impronta SHA256 dei **file sorgente reali**;
- proviene da un repository Aivexus posseduto dal progetto (Libreria,
  Ricercatore, Cantiere e altri), con commit immutabile, percorso
  `repository_path` e codice materializzato;
- i path sono sicuri, non contengono segreti/chiavi, non seguono symlink,
  non oltrepassano i limiti di dimensione e il codice non è stato alterato
  dopo l'evidenza di test.

Non serve una nuova firma di revisore, una variabile Actions esterna,
né un'attesa del Main/Reviewer per **preparare il pacchetto di prova**.
Il builder può usarlo **soltanto in ambiente isolato di sviluppo**, senza
permessi operativi, pubblicazione, installazione automatica o inclusione in
release. Se la licenza è ancora non chiarita, il pacchetto resta confinato
alla sperimentazione interna: non è autorizzazione alla redistribuzione.

Eventuali dipendenze vengono **dichiarate nei requisiti del pacchetto**,
senza essere scaricate o avviate dalla Libreria. Verranno verificate nei
test isolati del Cantiere: non sono un blocco alla scoperta/alla prova.

Il pacchetto espone `tier=sandbox_preview`, `certified=false`,
`production_approved=false`, i file sorgente verificati, digest immutabili,
piattaforme realmente testate e l'avvertenza d'uso.

Indice separato: `packages/experimental-index.json`

Pacchetti separati: `packages/experimental/<asset>/<version>/package.json`

La generazione è parte dell'autopilot sul branch protetto. Un sorgente cambiato,
un file non sicuro o una prova mancante non viene esportato. Il normale
`catalog/index.json` e `packages/index.json` rimangono **solo certificati**.

## Livello B — Certificato per produzione e distribuzione

La certificazione formale continua a richiedere verifiche legali,
sicurezza e licenze reali; una firma autenticata, quando richiesta dalla
politica di produzione, serve a confermare l'autorizzazione del revisore.
Non si può impostare `security.reviewed=true` per simulare un risultato,
né qualificare automaticamente una compatibilità Android/iOS mai verificata.

Le esigenze ad alto rischio (segreti, autenticazione, permessi, processi,
download o esecuzione arbitraria, plugin nativi, componenti esterni)
non possono essere implicitamente promosse dal livello sperimentale.

## Come misurare l'avanzamento

Il dashboard deve mostrare **separatamente**:

- moduli certificati per uso ordinario;
- moduli con codice reale testato e pacchetto sandbox disponibile;
- candidati ancora solo manifest/proposta o link a sorgenti esterne;
- motivi concreti dei blocchi residui.

Non chiamare "20 moduli disponibili" venti manifest: i puntatori esterni
senza sorgente restano indisponibili finché il codice non è recuperato.

### Comandi

```sh
python tools/library_experimental.py --export
python tools/library_experimental.py diagnostics.logging.library.privacy_events 0.1.0
python tools/library_autopilot.py
```

Questi comandi preparano soltanto artefatti locali con provenienza dichiarata.
Non installano né eseguono automaticamente il codice nel sistema ospite.
