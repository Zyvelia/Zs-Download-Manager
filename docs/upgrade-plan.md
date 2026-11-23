# Upgrade audit and acceptance criteria

## Baseline and scope

The audited project was commit `2c0b095`. It already had direct and torrent transfers, a three-slot HTTP queue, persistent JSON history, priorities, checksum quarantine, optional ZIP extraction, settings, a local browser bridge, and transfer cards. This upgrade preserves those interfaces and the existing history format; new record fields are optional. No supported control was removed.

The dashboard and Downloads page both expose the transfer list. Combining them could reduce repeated navigation, but would change a supported workflow; no consolidation has been made. Obtain the user's approval before removing either view.

## Ranked initiatives

| Rank | Type / initiative | User problem → capability and benefit | Dependencies; complexity; risk | Acceptance and affected modules |
|---|---|---|---|---|
| 1 | **Refinement — collision-safe partials** | Simultaneous downloads with the same URL filename could select the same `.part` path → exclusive reservation isolates their data. | HTTP engine and filesystem; medium; a crash can leave an empty partial. | Two simultaneous same-name transfers produce distinct, correct files; `engine.py`, `tests/upgrade_smoke.py`. |
| 2 | **New — batch transfer intake** | Repeated pasting is slow → paste lines or import a UTF-8 text file, preview valid/duplicate/invalid counts, confirm, and stop adding at any time. | Qt and existing engines; medium; imported links still require user trust. | At most 500 lines/1 MiB, duplicates skipped, only confirmed valid entries added in incremental batches; `workflows.py`, `ui.py`, batch tests. |
| 3 | **Refinement — resume completion recovery** | A full partial may receive HTTP 416 after restart → promote only if size and validator match; otherwise restart safely. | HTTP Range and validators; medium; servers without validators require a full restart. | Local server tests both matching and changed validators; `engine.py`, `tests/recovery_upgrade.py`. |
| 4 | **New — history backup recovery** | Corrupt history could strand transfer records → keep a validated prior snapshot and offer explicit recovery. | Same-directory atomic writes; medium; backup can be up to one save behind and contains the same sensitive URLs as history. | Legacy JSON list still loads; backup remains valid after corruption; recovery requires user confirmation; `history.py`, `ui.py`. |
| 5 | **Refinement — controlled retries** | Fixed indefinite retries can hammer unavailable servers → configurable retry count and exponential backoff, including selected transient HTTP statuses. | HTTP worker and timer; medium; elapsed retry times are approximate and server-specific `Retry-After` is not implemented. | 15 s initial delay, capped at 300 s; retry limit 0 preserves unlimited behavior; manual resume resets attempts; `engine.py`, `workflows.py`, `ui.py`. |
| 6 | **Refinement — adjustable queue** | Three concurrent HTTP slots do not suit every connection → user selects 1–20 while retaining priorities. | Existing queue and QSettings; low; too many slots can overload a server. | Default remains 3, decreasing the limit does not interrupt running transfers; `ui.py`, `tests/queue_smoke.py`. |
| 7 | **New — named workflow profiles** | Repeatedly changing destination, limits and automation is tedious → save/apply up to 20 named profiles. | QSettings; medium; profile destinations may not exist on another machine. | Validate all fields before applying; replacement asks for confirmation; profiles included in settings backup; `workflows.py`, `ui.py`. |
| 8 | **New — privacy-conscious activity log** | Transfer state changes are hard to diagnose → bounded rotating local state-transition log and viewer. | Standard logging; low; log still reveals activity timing and transfer type. | No URL, filename, token, or error string is written; 512 KiB per file plus two rotations; `diagnostics.py`, `ui.py`. |
| 9 | **Refinement — incremental list updates** | Adding/restoring many cards repeatedly filters and sorts the entire list → batch insertions defer expensive refreshes and yield to the event loop. | Qt event loop; medium; cards are still individual widgets, so very large histories remain expensive. | Batch handles 12 items per event-loop turn and refreshes once; stopped batches keep already added records; `ui.py`. |
| 10 | **Refinement — stop-aware network errors** | A connection error during pause/cancel could be reported as retryable instead of honoring the user's action → preserve requested state and clean canceled partials. | HTTP worker; low; a blocked read can still take the network timeout to stop. | Pause/cancel wins over an exception; cleanup failures are reported; `engine.py`. |

## Profiling and limits

A single local offscreen run inserting 100 cards individually took 0.606 s; inserting them with deferred filtering/sorting and one final refresh took 0.546 s. These are exploratory measurements on this environment, not a benchmark guarantee. The larger benefit is that the batch path yields every 12 cards. `QScrollArea` still creates one widget per transfer; a model/view virtualization is a future change and would require a broader UI migration.

## Deferred candidates

- Browser-store publishing, translations, configurable schedules, and full torrent file selection require separate design and platform/integration testing. They are not represented as finished features.
- OS credential vault support would require migrating existing URL-bearing history without losing resumability; this upgrade does not silently rewrite or remove existing records.
- Automatic destructive cleanup is deferred. History backup recovery and batch preview never delete downloaded data.
