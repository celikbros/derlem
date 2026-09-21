# TASK-043 — Retire-and-purge mechanism for superseded candidate objects

| Field | Value |
|---|---|
| Status | **DRAFT** — 2026-09-22; ~35 GB of dead candidates sit in the store with no legitimate way to remove them |
| Kind | ops (storage lifecycle) |
| Moratorium | allowed — housekeeping, no product surface |
| Estimate | 0.5 day |
| Depends on | — |
| Owner | (unassigned) |

## Why

Three superseded clean candidates hold about 35 GB in the content-addressed store: v1
(`ebe29279…`, 12.85 GB), v3 (`83dcac77…`, 11.9 GB), v4 (`23bfcdcf…`, 11.26 GB), plus their
held-out objects. None is referenced by any frozen release (every frozen release today is
`instruction` purpose). The owner asked for them to be deleted (2026-09-21, "gereksiz olan her
şeyi sil"), and there is currently **no correct way to do it**:

- Deleting the objects leaves `sources` rows pointing at missing files, which the restore
  drill's chain check reports as data loss.
- `deploy/known_lost_objects.txt` is the wrong instrument: its own rule says a line there means
  *accepting permanent data loss after recovery is exhausted*. Using it for deliberate cleanup
  would make the drill meaningless — "every missing object is a problem" is its current
  behaviour and that is the point.
- Deleting the `sources` rows requires deleting sampled documents, sample generations and
  reviews first (RESTRICT foreign keys), which destroys audit history — including the owner's
  three early document reviews on v1.

The cheap win was already taken: hard-linking the six raw-source objects to their archive
copies recovered 13.47 GB on 2026-09-21. That trick does not apply here, because the
candidates exist only in the store.

## Scope

- A `retired` lifecycle for a source, recorded through the product's own review path (decision
  `rejected` with a reason), so retirement is audited rather than surgical.
- Object purge for retired sources: the file is removed and `deploy/retired_objects.txt`
  records sha256, source id, reason, and the manifest that reproduces the artifact.
- Chain check (`deploy/scripts/derlem_restore_drill.py`) treats a retired source's missing
  object as intentional, and still fails on any other missing object.
- A written rule in [backup_restore.md](../backup_restore.md): what may be retired (never an
  object referenced by a frozen release; never a raw source that is the only copy) and what
  retirement costs (re-derivation time, stated per candidate from its manifest).
- Then retire the v1, v3 and v4 candidates and their held-outs — about 35 GB. All are
  reproducible from their manifests; note honestly that only runs from `tr-web-v3` onward
  record the interpreter and zlib version, so v1/v2-era candidates are reproducible in
  principle but not byte-guaranteed on a different interpreter.

## Out of scope

- Deleting anything referenced by a frozen release.
- Deleting raw sources or the parent corpus.
- Changing the immutability rule for objects still in use.

## Acceptance criteria

- [ ] Retirement appears in the audit trail (a review row), not only in a file.
- [ ] Drill passes with retired objects absent and still fails on an unlisted missing object
      (control run).
- [ ] v1, v3 and v4 candidates retired and purged; freed bytes measured; the backup mirror no
      longer carries them.

## Owner actions

- Confirm the three candidates are retirable. v1 carries three of the owner's own document
  reviews; those rows stay, only the bytes go.

## Report

(not started)
