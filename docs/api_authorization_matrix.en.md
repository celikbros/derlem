# API Authorization Matrix

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

**Date:** 2026-07-01
**Scope:** Derlem API read and write boundaries

This document is the canonical role contract for API authorization. Its code
counterpart is the fail-closed route table in
`internal/httpapi/authorization.go`. A new data endpoint cannot be registered
there without an explicit, non-empty role list.

## Roles

| Role | Data-access boundary |
|---|---|
| `admin` | All operational workspaces, release freeze, and artifact access |
| `data_manager` | Source management, jobs, draft/frozen releases, and artifacts |
| `editor` | Source workspace and document editing; no jobs, releases, or similarity |
| `moderator` | Source workspace and source/document/similarity review |
| `expert_reviewer` | The same sensitive review access as moderator |
| `contributor` | Session identity only for now; contribution workspace arrives in v0.5 |
| `consumer_team` | Frozen release metadata, manifests, and artifacts only |

## Endpoint Groups

| API group | Allowed roles | Additional boundary |
|---|---|---|
| `/api/v1/me` | Every authenticated role | Active user's identity and roles only |
| Auth logout/logout-all | Every authenticated role | Revokes the current or all server-side sessions |
| Source catalog/detail | `admin`, `data_manager`, `editor`, `moderator`, `expert_reviewer` | Closed to contributors and consumers |
| PII scans, sampled documents, quality, review history | `admin`, `data_manager`, `editor`, `moderator`, `expert_reviewer` | Raw/quarantined text uses the same boundary |
| Source creation and upload | `admin`, `data_manager` | Write operations are audited |
| Server-local file ingest | `admin` only | Path is restricted to `IMPORT_ROOT` and checked independently by API and worker |
| Source metadata update | `admin`, `data_manager`, `editor` | Optimistic version check required |
| Document content update | `admin`, `editor` | Creates a new immutable object version |
| Source/document/similarity decisions | `admin`, `moderator`, `expert_reviewer` | Self-review and blind-review rules also apply |
| Background jobs | `admin`, `data_manager` | Job payload/results are closed to other roles |
| Release list/detail | `admin`, `data_manager`, `consumer_team` | Consumers see only `frozen` releases and receive `404` for drafts |
| Release creation/export | `admin`, `data_manager` | Exports are built only from frozen releases |
| Release freeze | `admin` | Human critical gate |
| Frozen manifest/source/export download | `admin`, `data_manager`, `consumer_team` | Repository query also enforces `release.status='frozen'` |
| Similarity run/pair/full text | `admin`, `moderator`, `expert_reviewer` | Other reviewers' evidence is blinded before a decision |

## Security Rules

- Missing identity returns `401`; insufficient role returns `403`.
- A consumer's draft-release detail request returns `404` to avoid disclosing
  that the draft exists.
- Hidden navigation is not a security control; the Go API makes the decision.
- General source read access is not granted to `contributor` before source
  ownership exists.
- Source/project ACLs remain tracked under `SEC-P1-02` before public or
  multi-tenant contribution.

## Verification

`internal/httpapi/authorization_test.go` tests every protected GET endpoint
against all seven application roles, including positive and negative cases. It
also requires each protected route to carry a non-empty policy made only from
known roles.

```powershell
go test ./internal/httpapi
```
