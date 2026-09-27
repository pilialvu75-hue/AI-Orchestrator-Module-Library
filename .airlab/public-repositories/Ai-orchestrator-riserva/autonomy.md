# Esecuzione autonoma della roadmap Riserva

Autorizzata dall'utente il 27 settembre 2026 nella chat dell'audit consolidato.
Esecutore: attività programmata ChatGPT **Avanza roadmap Riserva**.
ID operativo: `6ab936e182e88191a138246790477161`.
Ripresa oraria, fuso Europe/Paris. Le esecuzioni usano le risorse già autorizzate
e restano soggette ai limiti di utilizzo: questa configurazione non garantisce
un servizio continuo né attiva API, acquisti o crediti aggiuntivi.

## Fonti e ambito

- Codice: `pilialvu75-hue/Ai-orchestrator-riserva`, main corrente.
- Roadmap: `roadmap.yaml` in questa directory sul main della Library.
- Checkpoint operativo: `execution.json` in questa directory, **esclusivamente
  sul branch `automation/riserva-state` della Library**.
- Prima di ogni ciclo leggere handoff, roadmap, state e decisions della Library
  e le istruzioni applicabili del repository da modificare.
- Conservare questa documentazione e lo stato nella Library privata.
  Le PR pubbliche descrivono il problema tecnico senza divulgare la roadmap.
- Il branch operativo contiene solo checkpoint; non viene fuso in main e non
  ospita codice da eseguire. I workflow attuali della Library partono dai push
  su main e dalle PR: i checkpoint non producono build inutili.
- Le modifiche di codice e i cambiamenti di stato della roadmap seguono PR,
  review e CI. Non modificare workflow per saltare gate richiesti.

## Stato durevole e esclusione reciproca

Lo stato è un documento JSON con schema_version, enabled, automation_id,
target_repository, last_observed_main, lease, current_work, deferred_work,
completed_work, last_run, last_notification e next_action.

1. Leggere il checkpoint dal branch operativo e il suo blob SHA.
2. Se enabled è false, terminare. Se lease non è null e expires_at è nel
   futuro, un altro ciclo è proprietario: terminare senza scritture.
3. Per acquisire la lease generare un owner_run_id univoco e impostare
   acquired_at, heartbeat_at, expires_at (ora UTC + 45 minuti).
   Scrivere execution.json con l'esatto blob SHA letto tramite Contents API.
   Su conflitto rileggere: mai forzare o sovrascrivere uno stato più nuovo.
4. Rileggere e verificare il proprio owner_run_id. Se non coincide, fermarsi.
   Prima di ogni mutazione esterna ricontrollare proprietà e scadenza; se
   necessario rinnovare con la stessa scrittura condizionale.
5. Una lease scaduta non cancella current_work: prima di subentrare
   riconciliare commit, PR e run remoti. Non duplicare un dispatch.
6. Ogni checkpoint preserva i dati altrui e usa l'ultimo SHA letto.
   Su errore di scrittura o perdita della lease fermare le mutazioni.
7. Al termine salvare last_run/next_action e porre lease a null.
   Un crash lascia uno stato recuperabile dopo scadenza.

Questo è un protocollo cooperativo tra gli esecutori che lo rispettano,
non un blocco imposto da GitHub a tutte le altre chat. Controllare PR e
attività concorrenti prima delle scritture; usare expected_head_sha per merge.
Non sovrascrivere branch attivamente usati da altre lavorazioni.

## Selezione e avanzamento

Prima riconciliare current_work, poi scegliere dal delivery_order della
roadmap il primo incremento realmente affrontabile. Verificare dipendenze,
stato attuale e criteri done_when. Recuperare selettivamente PR esistenti:
il primo candidato rilevato è CANT-AUDIT-01 / #608, in conflitto alla
verifica iniziale; non considerare questo snapshot una condizione permanente.

Una sola PR di implementazione gestita attivamente dall'esecutore.
Sono consentite le PR private della relativa roadmap. Un solo nuovo incremento
per ciclo; massimo 25 minuti di lavoro attivo e due correzioni successive
a fallimenti CI per incremento. I contatori persistono, non si azzerano
al ciclo successivo.

Fasi operative: READY, IMPLEMENTING, WAITING_CI, READY_FOR_REVIEW,
READY_FOR_DEVICE, BLOCKED, COMPLETED. Salvare almeno finding_id,
increment_id, branch, PR, base/head SHA, CI run IDs, tentativi, evidenze,
prossimo passo e blocco concreto.

- Se CI è in corso, salvare WAITING_CI e terminare. Il ciclo successivo legge
  lo stesso run, senza lanciare un'altra build.
- Dopo il limite di correzioni, salvare BLOCKED con log e diagnosi.
- Un task bloccato su input/test fisico può passare a deferred_work;
  la sua PR resta aperta, non viene abbandonata. Ricontrollarlo prima di un
  task nuovo e non iniziare lavori che ne dipendano o si sovrappongano.
- Un risultato già assorbito da main richiede verifica del codice e dei
  criteri, non una seconda implementazione.
- Lo stato COMPLETED richiede le evidenze di tutti i criteri applicabili;
  PR aperta, CI verde e test fisico sono condizioni distinte.

## Merge, release e test reali

Preparare o eseguire il merge solo entro l'autorizzazione esistente, dopo
review del diff, nessuna richiesta di modifica irrisolta, verifiche pertinenti
concluse verdi sull'esatto head e compatibilità con main. Usare expected_head_sha
e ricontrollare main tra due merge.

Il verde CI non certifica un'app sul telefono. Rispettare ogni gate fisico
esplicito delle PR, in particolare runtime, memoria, GPU e prima app Cantiere.
Controllare gli effetti dei workflow prima del merge: se il push innesca
una distribuzione stabile priva del gate fisico richiesto, mantenere la PR
READY_FOR_DEVICE/READY_FOR_REVIEW e richiedere soltanto quella verifica reale.
Non aggirare il vincolo modificando la CI.

Aggiornare roadmap e stato pertinente nella stessa PR privata quando cambia
un elemento; registrare nuove decisioni secondo handoff. Il checkpoint
operativo mantiene il link a questa PR senza confondere il suo esito con
quello della PR di codice. Evitare regressioni di checkpoint: non fondere
il branch operativo in main.

## Vincoli e comunicazione

Preservare offline-first, separazione delle impostazioni Assistente/Cantiere,
controlli di memoria e cancellazione, review/validation/approval/apply,
certificazione Library e privacy Diagnostics. Nessuna cancellazione massiva
di branch, force-push, refactor generale o attivazione sync senza i suoi gate.
Non creare sotto-agenti o altre automazioni e non contattare persone.

Non acquistare crediti, cambiare budget o abbonamenti, attivare API a pagamento
o modificare credenziali. Se manca una risorsa o si raggiunge un limite,
registrare il blocco reale senza dichiarare lavoro eseguito.

Notificare in italiano solo avanzamenti verificati, PR/build pronte o nuovi
blocchi che richiedono l'utente. Persistire una chiave last_notification
basata su finding/head/esito per evitare ripetizioni. Non chiedere "continua".
Quando ogni elemento autorizzato è concluso, salvare lo stato finale,
impostare enabled=false e disattivare l'attività programmata.
