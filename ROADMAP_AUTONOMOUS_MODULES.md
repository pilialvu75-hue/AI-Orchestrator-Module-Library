# Roadmap operativa — Libreria AIVEXUS autonoma

Aggiornamento: 2026-11-07. Fonte di verità per il percorso P0 fino al primo modulo autonomo realmente utilizzabile.

## Decisione vincolante: prima i risultati

La metrica primaria non è il numero di PR, controlli o workflow: è il numero di **moduli nuovi scoperti, acquisiti, adattati, collaudati e integrati automaticamente**, con un consumer indipendente funzionante. Non sostituire il lavoro produttivo con ulteriori barriere o perfezionamenti non necessari. Mantenere isolamento dell'esecuzione esterna e provenienza verificabile.

## P0 — Dimostrazione end-to-end, senza preparazione manuale del candidato

1. **Scoperta esterna reale**: il Ricercatore consulta un ecosistema pubblico e individua un pacchetto non presente nell'elenco fisso `path/characters/fixnum`. Registrare fonte, commit/tag e criteri di scelta. PR #284 introduce un primo inventario dinamico da `dart-lang/core`; non è ancora una catena completa.
2. **Acquisizione automatica**: scaricare il sorgente del candidato selezionato, conservare hash dei file, licenza, dipendenze e provenienza; nessuna modifica manuale preparatoria.
3. **Valutazione e adattamento**: ricavare capacità e contratto del modulo; generare un adattatore Dart reale che importi il codice esterno, senza simulazioni o test che ripetano soltanto costanti.
4. **Collaudo isolato**: installare dipendenze, analizzare/compilare, eseguire test funzionali su input e casi limite; pubblicare log, commit e risultati riproducibili. Gli errori devono produrre diagnosi e tentativi di correzione automatica limitati.
5. **Consumer indipendente**: creare ed eseguire una piccola applicazione esterna al payload della Libreria che importi l'adattatore e dimostri il comportamento richiesto.
6. **Integrazione automatica**: dopo CI PASS, registrare sorgente, manifest, adattatore, prove e contratto nella Libreria come `TESTED`. Verificare che un secondo consumer possa riutilizzarlo.
7. **Ripetibilità**: ripetere l'intero percorso senza interventi manuali con almeno altri due moduli diversi; obiettivi progressivi: **1 → 3 → 10 moduli utilizzabili**.

**Definition of Done P0**: almeno un pacchetto nuovo non preselezionato, acquisito da upstream, adattato, testato e realmente usato da consumer separato; PR e merge automatici con CI verde; manifest `TESTED` con prove consultabili; nessuna operazione manuale di preparazione del modulo. Se manca un passaggio, l'autonomia non è raggiunta.

## P1 — Dopo il primo risultato funzionale

- Migliorare selezione e ranking dei candidati rispetto alle esigenze reali del Cantiere.
- Generalizzare la creazione degli adattatori a pacchetti, linguaggi e piattaforme differenti.
- Aumentare robustezza, velocità, parallelismo, gestione errori, qualità e copertura dei test.
- Revisione indipendente di sicurezza, licenza e privacy; firma protetta e passaggio esplicito da `TESTED` a `CERTIFIED`. Mai confondere un test funzionale con una certificazione.
- Misurare riuso reale, integrazioni riuscite/fallite, regressioni, costi e valore prodotto.
- Collegare i moduli collaudati al Cantiere, che li seleziona per capacità e contratto e ne prova l'integrazione nelle app.

## Stato e riferimenti (non confondere preparazione con risultato)

- PR #275–#281: integrità, test consumer `fixnum`, review indipendente e correzioni infrastrutturali.
- PR #282: inventario di candidati sconosciuti, **merged**.
- PR #283: CLI di discovery locale, **merged**.
- PR #284: discovery reale del catalogo pubblico Dart, **aperta al momento di questa roadmap**; da verificare CI e integrare.
- `fixnum`: consumer reale testato, ma candidato già preparato; `TESTED`, **non** prova del ciclo autonomo né `CERTIFIED`.
- Issue #219: obiettivo di certificazione autonoma end-to-end, successivo alla dimostrazione P0 funzionale.

## Regole di avanzamento

- Per ogni fase: codice reale su GitHub, test eseguiti, risultati verificabili, stato CI, PR/merge e blocco concreto successivo.
- Merge periodici su `main` quando la CI è verde, senza attendere perfezione teorica.
- Non dichiarare completato ciò che è soltanto progettato, simulato o parzialmente automatizzato.
- Evitare nuove PR dedicate esclusivamente a divieti/controlli se non risolvono un blocco concreto del percorso produttivo.
- Conservare la distinzione `DISCOVERED` / `UNTRUSTED` / `TESTED` / `CERTIFIED` e non eseguire codice sconosciuto fuori dall'ambiente isolato.
