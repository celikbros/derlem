# TASK-003 — Large release downloads are cut off by the server write timeout

| Field | Value |
|---|---|
| Status | **IN REVIEW** — code done 2026-09-12; needs the full-size human check (see Report) |
| Kind | fix |
| Moratorium | allowed (defect, no new behaviour) |
| Estimate | 2–3 h (fix ~30 min; the regression test and a real full-size download take the rest) |
| Owner | (unassigned) |
| Verified against code | 2026-09-12 |

## Goal

Make every frozen-release download complete regardless of size. Today a download
is killed after 30 seconds, which makes the largest artifact (13 GB) impossible
to fetch through the API.

## Why

`consumer_team` exists for exactly one purpose: downloading frozen releases and
verifying their checksums (`web/lib/roles.ts`, role `consumer_team`). That path is
currently broken for anything larger than a few hundred megabytes, so the last
link of the delivery chain does not work. This is not a scale problem — **one**
user triggers it.

**Severity is latent, not active.** The two multi-GB objects in the store are
*source uploads* and belong to no release, and every body the download routes can
currently serve is a few kilobytes — so nobody has been able to hit this yet. It
fires the moment a release includes a real corpus source, which is precisely what
release #1 is meant to do. That, plus zero test coverage on these four routes, is
why it survived unnoticed.

## Current state (measured)

`cmd/api/main.go:67-74` configures the shared HTTP server:

```go
ReadHeaderTimeout: 5 * time.Second,
ReadTimeout:       15 * time.Second,
WriteTimeout:      30 * time.Second,
IdleTimeout:       2 * time.Minute,
```

`http.Server.WriteTimeout` is a deadline on the **whole** response, not an idle
timeout. Once it expires mid-body the connection is torn down.

Four endpoints serve object bodies through that server
(`internal/httpapi/authorization.go:96-99`):

| Route | Handler |
|---|---|
| `GET /api/v1/releases/{id}/manifest` | `downloadReleaseManifest` |
| `GET /api/v1/releases/{id}/exports/{format}/artifact` | `downloadReleaseExport` |
| `GET /api/v1/releases/{id}/exports/{format}/manifest` | `downloadReleaseExportManifest` |
| `GET /api/v1/releases/{id}/sources/{source_id}/artifact` | `downloadReleaseSource` |

All four funnel into `streamReleaseArtifact` (`internal/httpapi/release_handlers.go:206-224`),
whose body copy is a bare `io.Copy(w, reader)` — no deadline handling.

Object sizes in the live database — 742 objects, 25 GB total, largest 13 GB. The
two largest are source uploads not yet attached to a release:

| Object | Size | Owner | In a release? |
|---|---|---|---|
| `9826d58e…` | 13 GB | source `gardash_faz2_tr_dedup_20260621` | no |
| `ebe29279…` | 12 GB | source `…_20260621_cle…` | no |
| `ebbc199c…` | 1707 B | `release_exports` (jsonl, Canonical Export Smoke) | yes, frozen |

13 GB within 30 s requires **433 MB/s** sustained. On gigabit LAN (~110 MB/s) the
transfer needs ~2 minutes and is cut at 30 s. The threshold on such a link is about
**3.3 GB** — every corpus source of a realistic size is above it.

**The upload path already solved this** (`internal/httpapi/upload_handlers.go:20-24`):

```go
controller := http.NewResponseController(w)
_ = controller.SetReadDeadline(time.Time{})
_ = controller.SetWriteDeadline(time.Time{})
```

So the system accepts 50 GB uploads (`MAX_UPLOAD_BYTES` default `50*1024*1024*1024`,
`internal/config/config.go:79`) but refuses to serve 13 GB back. This card closes
that asymmetry — it is an oversight in one function, not a design question.

**Test coverage:** `internal/httpapi/release_handlers_test.go` is 16 lines and
covers only `safeDownloadName`. Nothing exercises `streamReleaseArtifact`, and no
test anywhere in `internal/httpapi/` touches the deadline pattern. That is why the
defect survived.

## Scope

1. New file `internal/httpapi/download_deadline.go` with a copy helper that
   refreshes the write deadline as the transfer makes progress.
2. `streamReleaseArtifact`: replace `io.Copy(w, reader)` with that helper.
3. New file `internal/httpapi/download_deadline_test.go` with a regression test
   driven by a **real** `http.Server` (a recorder cannot reproduce this — see Risks).

## Out of scope

- The upload path's deadlines. They work; do not touch them.
- `ReadTimeout` / `IdleTimeout` / `ReadHeaderTimeout` on the shared server. Leaving
  the 30 s `WriteTimeout` in place is deliberate: it still protects every ordinary
  JSON endpoint, and only the download path opts out of it.
- HTTP range requests / resumable downloads. Worth doing later (a 13 GB transfer
  that fails at 90 % restarts from zero today), but it is a new capability, not this
  defect. Note it for the owner.
- Moving objects to MinIO/S3 with presigned URLs. That is the Faz D answer
  (`docs/scalability_architecture.md`) and removes these handlers from the hot path
  entirely; it is not a prerequisite for fixing the defect.

## Design / approach

Do **not** clear the write deadline outright (`SetWriteDeadline(time.Time{})`),
even though that is what the upload handler does. A download is served to a client
that may simply stop reading; with no deadline at all the goroutine, the socket and
the open object file handle are pinned indefinitely, and an authenticated
`consumer_team` account could exhaust file descriptors by opening many downloads
and reading none.

Instead, keep a deadline but **refresh it while the transfer progresses**. The
semantics become "no total time limit, but the client must keep making progress",
which is what a large download actually needs:

- write in fixed chunks (1 MiB, matching `io.CopyBuffer`'s buffer in the upload path)
- after every 4 MiB written, push the write deadline out by 2 minutes
- if `SetWriteDeadline` is unsupported by the wrapper, fall through to the plain
  copy so behaviour is never worse than today

`io.Copy` / `io.CopyBuffer` must **not** be used for this: they delegate to
`io.ReaderFrom` / `io.WriterTo` when available, which can hand the whole file to a
single `sendfile` call. The deadline would then never be refreshed mid-transfer and
the bug would survive. The helper therefore runs an explicit read/write loop.

The tunables are parameters of an inner function so the test can shrink them; the
exported behaviour uses the package constants.

## Files

- `internal/httpapi/download_deadline.go` (new)
- `internal/httpapi/download_deadline_test.go` (new)
- `internal/httpapi/release_handlers.go` (`streamReleaseArtifact`, body copy only)

## Acceptance criteria

- [ ] `go build ./... && go vet ./...` clean.
- [ ] `go test ./internal/httpapi/` passes.
- [ ] The new test starts a real `http.Server` with `WriteTimeout` set to a few
      hundred milliseconds, streams a body whose writes span several times that
      duration, and asserts the client receives **every** byte.
- [ ] The same test asserts the control case — the identical stream copied with
      plain `io.Copy` — **fails**. Without this the test could pass vacuously and
      prove nothing.
- [ ] A client that stops reading is still disconnected (the deadline is refreshed,
      not removed). Covered by a stalled-reader subtest or, failing that, stated as
      an explicit gap in the Report.
- [ ] Manual, on a running stack: `consumer_team` completes a download whose
      **duration** exceeds 30 s and the SHA256 matches `release_exports.object_sha256`.
      **This is the real acceptance test; the unit test only prevents regression.**

## Verification commands

```powershell
go build ./...; go vet ./...; go test ./internal/httpapi/
```

### End-to-end check — throttle, do not inflate

The defect is governed by **elapsed time, not payload size**, so the test must make
the transfer slow, not big. Do not try to reproduce it by downloading the 13 GB
object:

- that object is a **source upload** (`sources.object_sha256`,
  `gardash_faz2_tr_dedup_20260621`) and belongs to **no release**, so no download
  route exposes it today;
- the largest body any route currently serves is a **1707-byte** JSONL export;
- over localhost a multi-GB body moves at ~1 GB/s, finishes inside 30 s and so
  never trips the deadline — the test would pass even against the unfixed code.

`curl --limit-rate` reproduces it exactly, with the client slowness under our
control instead of left to chance. 1707 bytes at 40 B/s ≈ 43 s, comfortably past
the 30 s `WriteTimeout`:

```powershell
# API only; worker and web are not needed for this check.
$login = Invoke-RestMethod -Method Post -Uri http://localhost:18401/api/v1/auth/login `
  -ContentType 'application/json' `
  -Body (@{ email = 'consumer@derlem.local'; password = 'DerlemTest123!' } | ConvertTo-Json)

$release = 'f442baba-43dc-4da8-a201-d57b34ed0012'   # Canonical Export Smoke (frozen)

Measure-Command {
  curl.exe -sS --limit-rate 40 -H "Authorization: Bearer $($login.token)" `
    -o export.jsonl "http://localhost:18401/api/v1/releases/$release/exports/jsonl/artifact"
}
(Get-Item export.jsonl).Length          # expect 1707
(Get-FileHash export.jsonl -Algorithm SHA256).Hash.ToLower()
```

Expected: elapsed **> 30 s**, length exactly `1707`, hash equal to
`ebbc199c42151b276411209856b53dcaa7a9b4e9f8b281c5ead187810bf5c699`.

Against the unfixed code the same command dies mid-body with a partial file — which
is what makes this a real reproduction rather than a smoke test.

Cross-check the expected values from the database:

```sql
SELECT object_sha256, byte_size
FROM public.release_exports
WHERE release_id = 'f442baba-43dc-4da8-a201-d57b34ed0012' AND format = 'jsonl';
```

## Risks / traps

- **`httptest.NewRecorder` cannot reproduce this.** `http.ResponseController` on a
  recorder returns `http.ErrNotSupported`, and a recorder has no deadlines at all,
  so a recorder-based test passes both before and after the fix. The test must use
  `httptest.NewUnstartedServer`, set `srv.Config.WriteTimeout`, then `Start()`.
- **Do not reintroduce `io.Copy`** in `streamReleaseArtifact` during a later
  refactor; see Design for why it defeats the fix. The helper's doc comment says so.
- `Content-Length` is set before the body is written
  (`release_handlers.go:217`). It stays correct — the fix changes only how the bytes
  are copied, not how many.
- A write error mid-body cannot be turned into an HTTP error status; the header has
  already gone out. Keep the existing `s.logger.Warn(...)` on interruption.
- Timing-based tests are flaky if margins are tight. Use a slow source with sleeps
  so the elapsed write phase exceeds the deadline by a wide multiple, rather than
  relying on payload size and socket buffering.

## Report

**Code complete 2026-09-12.** Implemented as designed.

- `internal/httpapi/download_deadline.go` (new): `copyDownloadBody` plus the
  parameterised `copyRefreshingDeadline`. Explicit 1 MiB read/write loop; the write
  deadline is pushed out 2 minutes after every 4 MiB. If `SetWriteDeadline` is
  unsupported the loop still runs, just without refreshing — never worse than before.
- `internal/httpapi/release_handlers.go`: `streamReleaseArtifact` now calls
  `copyDownloadBody`; the `io` import became unused and was dropped. All four
  download routes share this function, so one change covers every one of them.
- `internal/httpapi/download_deadline_test.go` (new): three tests on a real
  `httptest.NewUnstartedServer` with `WriteTimeout` at 200 ms and a source that
  spans ~600 ms of writes.

**Verification run:**

- `go build ./...` clean; `go vet ./internal/httpapi/` clean
- `go test ./internal/httpapi/` → ok
- `go test ./...` → all packages ok, no regressions
- `-count=8` on the three new tests → ok (10.0 s), no flakiness across repeats

**The control test earned its place.** `TestPlainCopyIsCutByWriteTimeout` copies the
identical stream with plain `io.Copy` and the server log shows the real defect:

```
write tcp 127.0.0.1:54165->127.0.0.1:54166: i/o timeout
```

while the fixed path delivered all 1 MiB. So the fix is demonstrated against a
reproduction of the bug, not merely asserted.

`TestCopyDownloadBodyDropsStalledClient` confirms the deadline was **refreshed, not
removed**: a client that never reads is dropped. Had the deadline been cleared
outright — the pattern the upload handler uses — that test would hang and fail.

**Not verified (honest gap):** no end-to-end download was performed. The API is
stopped and Derlem services are started by the owner, not from here. The unit tests
prove the deadline no longer caps the transfer; they do not prove the handler wiring
serves a complete body over a real socket. **The last acceptance criterion is still
open** — the throttled `curl.exe` recipe under Verification commands, which takes
about a minute.

**Correction made while writing this Report.** The card first described the problem
as "the 13 GB export cannot be downloaded". Measurement showed otherwise: the 13 GB
object is a *source upload* attached to no release, and the biggest body the
download routes serve today is 1707 bytes. The defect is unchanged — the deadline
still caps every transfer at 30 s — but it is **latent** rather than actively
breaking something, and the verification recipe had to change from "download 13 GB"
to "throttle a small download past 30 s". The original recipe would have passed
against the unfixed code and proved nothing.

**Observations for the owner (not changed here):**

1. **No range/resume support.** A 13 GB transfer that dies at 90 % restarts from
   zero. Worth a card of its own; `Content-Range` plus `Accept-Ranges` on these four
   routes would also let clients parallelise.
2. **The upload path clears its deadlines entirely** (`upload_handlers.go:22-23`)
   rather than refreshing them. It works, and it is out of scope here, but a client
   that opens an upload and then sends nothing pins a connection indefinitely. The
   same refresh approach would close that; left alone deliberately.
3. This defect existed because **no test touched the download handlers at all**.
   `release_handlers_test.go` was 16 lines covering one string helper. The four
   routes that are `consumer_team`'s entire reason to log in had zero coverage.
