"use client";

import {
  Archive,
  ChartBar,
  Check,
  Download,
  FileArchive,
  FileJson,
  FileText,
  Files,
  LockKeyhole,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { messageFrom, requestJSON } from "@/lib/client-api";
import type { Release, Source, User } from "@/lib/types";

const purposes = ["pretrain", "instruction", "preference", "eval", "holdout", "post_training"];

export function ReleasePanel({
  sources,
  user,
  onNotice,
}: {
  sources: Source[];
  user: User;
  onNotice: (message: string) => void;
}) {
  const [releases, setReleases] = useState<Release[]>([]);
  const [selected, setSelected] = useState<Release | null>(null);
  const [purpose, setPurpose] = useState("instruction");
  const [selectedSourceIDs, setSelectedSourceIDs] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [freezing, setFreezing] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const createDialog = useRef<HTMLDialogElement>(null);
  const canManage = user.roles.some((role) => ["admin", "data_manager"].includes(role));
  const canFreeze = user.roles.includes("admin");
  const canDownload = user.roles.some((role) => ["admin", "data_manager", "consumer_team"].includes(role));

  const loadReleases = useCallback(async () => {
    try {
      const payload = await requestJSON<{ items: Release[] }>("/api/releases");
      setReleases(payload.items);
      setSelected((current) => current
        ? payload.items.find((release) => release.id === current.id) ?? null
        : payload.items[0] ?? null);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadReleases(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadReleases]);

  const eligibleSources = useMemo(
    () => sources.filter((source) =>
      source.approval_status === "approved_source" && source.content_purpose === purpose),
    [purpose, sources],
  );

  async function createRelease(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedSourceIDs.size === 0) {
      onNotice("En az bir onaylı kaynak seçilmelidir.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const release = await requestJSON<Release>("/api/releases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: data.get("name"),
          version: data.get("version"),
          content_purpose: purpose,
          source_ids: [...selectedSourceIDs],
        }),
      });
      setReleases((current) => [release, ...current]);
      setSelected(release);
      setSelectedSourceIDs(new Set());
      form.reset();
      createDialog.current?.close();
      onNotice("Draft release oluşturuldu.");
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }

  async function freezeRelease(release: Release) {
    setFreezing(release.id);
    try {
      await requestJSON<{ job_id: string }>(`/api/releases/${release.id}/freeze`, { method: "POST" });
      onNotice("Freeze işi kuyruğa alındı.");
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await delay(750);
        const updated = await requestJSON<Release>(`/api/releases/${release.id}`);
        setReleases((current) => current.map((item) => item.id === updated.id ? updated : item));
        setSelected(updated);
        if (updated.status === "frozen") {
          onNotice("Release donduruldu ve manifest üretildi.");
          return;
        }
        if (Object.keys(updated.gate_results ?? {}).length > 0) {
          onNotice("Freeze kalite kapısı tarafından durduruldu.");
          return;
        }
      }
      onNotice("Freeze işi çalışmaya devam ediyor; Sürümler görünümünden yenileyebilirsiniz.");
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setFreezing(null);
    }
  }

  async function createExport(release: Release, format: "jsonl" | "txt") {
    setExporting(format);
    try {
      await requestJSON<{ job_id: string }>(`/api/releases/${release.id}/exports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format }),
      });
      onNotice(`${format.toUpperCase()} export işi kuyruğa alındı.`);
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await delay(1000);
        const updated = await requestJSON<Release>(`/api/releases/${release.id}`);
        setReleases((current) => current.map((item) => item.id === updated.id ? updated : item));
        setSelected(updated);
        const currentExport = updated.exports.find((item) => item.format === format);
        if (currentExport?.status === "ready") {
          onNotice(`${format.toUpperCase()} export hazır.`);
          return;
        }
        if (currentExport?.status === "failed") {
          onNotice(currentExport.last_error ?? "Export işi başarısız oldu.");
          return;
        }
      }
      onNotice("Export arka planda çalışıyor; İşler görünümünden ilerlemeyi izleyebilirsiniz.");
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setExporting(null);
    }
  }

  function toggleSource(sourceID: string, checked: boolean) {
    setSelectedSourceIDs((current) => {
      const next = new Set(current);
      if (checked) next.add(sourceID);
      else next.delete(sourceID);
      return next;
    });
  }

  const selectedMixture = selected ? mixtureReport(selected) : undefined;
  const selectedNearDuplicates = selected ? nearDuplicateReport(selected) : undefined;

  return (
    <section className={`release-layout${selected ? " with-detail" : ""}`}>
      <div className="release-list-panel">
        <div className="table-toolbar release-toolbar">
          <div>
            <strong>Frozen veri teslimleri</strong>
            <span>{releases.length} sürüm</span>
          </div>
          <div className="toolbar-actions">
            <button className="icon-button" type="button" title="Sürümleri yenile" onClick={() => { setLoading(true); void loadReleases(); }}>
              <RefreshCw className={loading ? "spin" : ""} size={18} />
            </button>
            {canManage && (
              <button className="primary-button" type="button" onClick={() => createDialog.current?.showModal()}>
                <Plus size={17} />Yeni release
              </button>
            )}
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Release</th><th>Amaç</th><th>Durum</th><th>Kaynak</th></tr></thead>
            <tbody>
              {releases.map((release) => (
                <tr key={release.id} className={selected?.id === release.id ? "selected-row" : undefined}>
                  <td><button className="source-link" type="button" onClick={() => setSelected(release)}><strong>{release.name}</strong><span>{release.version} · {releaseStatusLabel(release.status)}</span></button></td>
                  <td><span className="purpose-label">{release.content_purpose}</span></td>
                  <td><ReleaseStatus value={release.status} /></td>
                  <td>{release.sources.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && releases.length === 0 && (
            <div className="empty-state"><FileArchive size={25} /><p>Henüz release oluşturulmadı.</p></div>
          )}
        </div>
      </div>

      {selected && (
        <aside className="release-detail">
          <div className="release-detail-header">
            <div><span>Release ayrıntısı</span><h2>{selected.name}</h2><p>{selected.version}</p></div>
            <button className="icon-button" type="button" title="Ayrıntıyı kapat" onClick={() => setSelected(null)}><X size={19} /></button>
          </div>
          <div className="release-facts">
            <Fact label="Amaç" value={selected.content_purpose} />
            <Fact label="Durum" value={selected.status} />
            <Fact label="Kaynak sayısı" value={String(selected.sources.length)} />
            <Fact label="Oluşturulma" value={formatDate(selected.created_at)} />
            {selected.frozen_at && <Fact label="Freeze zamanı" value={formatDate(selected.frozen_at)} />}
          </div>

          {selected.status === "draft" && canFreeze && (
            <button className="primary-button release-freeze-button" type="button" disabled={freezing === selected.id} onClick={() => void freezeRelease(selected)}>
              <LockKeyhole size={17} />{freezing === selected.id ? "Donduruluyor" : "Release'i dondur"}
            </button>
          )}

          <section className="release-section">
            <h3><ShieldCheck size={16} /> Kalite kapıları</h3>
            <div className="gate-result-list">
              {gateRows(selected).map((gate) => <div key={gate.label}><span>{gate.label}</span><strong className={gate.status}>{gate.text}</strong></div>)}
            </div>
          </section>

          {selectedNearDuplicates && (
            <section className="release-section">
              <h3><Files size={16} /> Yakın tekrar raporu</h3>
              <div className="near-duplicate-summary">
                <div className="mixture-totals">
                  <span>{selectedNearDuplicates.indexed_document_count.toLocaleString("tr-TR")} indeks</span>
                  <span>{selectedNearDuplicates.potential_pair_count.toLocaleString("tr-TR")} çift</span>
                  <span>{selectedNearDuplicates.candidate_overflow_document_count.toLocaleString("tr-TR")} taşma</span>
                </div>
                <div className="near-duplicate-breakdown">
                  <div><span>Kaynak içi</span><strong>{selectedNearDuplicates.within_source_pair_count.toLocaleString("tr-TR")}</strong></div>
                  <div><span>Kaynaklar arası</span><strong>{selectedNearDuplicates.cross_source_pair_count.toLocaleString("tr-TR")}</strong></div>
                  <div><span>Hamming eşiği</span><strong>≤ {selectedNearDuplicates.hamming_threshold}</strong></div>
                </div>
                {selectedNearDuplicates.sample_pairs.length > 0 && (
                  <div className="near-duplicate-samples">
                    <strong>Örnek çiftler</strong>
                    {selectedNearDuplicates.sample_pairs.slice(0, 5).map((pair) => {
                      const source = releaseSourceLabel(selected, pair.source_sha256);
                      const matched = releaseSourceLabel(selected, pair.matched_source_sha256);
                      const label = `${source} #${pair.source_ordinal} ↔ ${matched} #${pair.matched_source_ordinal}`;
                      return <div key={`${pair.source_sha256}:${pair.source_ordinal}:${pair.matched_source_sha256}:${pair.matched_source_ordinal}`}><span title={label}>{label}</span><b>d={pair.hamming_distance}</b></div>;
                    })}
                  </div>
                )}
              </div>
            </section>
          )}

          {selectedMixture && (
            <section className="release-section">
              <h3><ChartBar size={16} /> Veri karışımı</h3>
              <div className="mixture-summary">
                <div className="mixture-totals">
                  <span>{selectedMixture.totals.source_count.toLocaleString("tr-TR")} kaynak</span>
                  <span>{formatBytes(selectedMixture.totals.byte_size)}</span>
                  <span>{selectedMixture.totals.line_count.toLocaleString("tr-TR")} kayıt</span>
                </div>
                <MixtureDimension label="Dil" entries={selectedMixture.dimensions.language} />
                <MixtureDimension label="Alan" entries={selectedMixture.dimensions.domain} />
                <MixtureDimension label="Kaynak tipi" entries={selectedMixture.dimensions.source_type} />
                <MixtureDimension label="Lisans" entries={selectedMixture.dimensions.license} />
                {selectedMixture.quality && <QualityMixtureSummary quality={selectedMixture.quality} />}
              </div>
            </section>
          )}

          <section className="release-section">
            <h3><Archive size={16} /> Frozen kaynaklar</h3>
            <div className="release-artifacts">
              {selected.sources.map((source) => (
                <div key={source.source_id}>
                  <div><strong>{source.source_name}</strong><code>{source.source_sha256}</code></div>
                  {selected.status === "frozen" && canDownload && (
                    <a className="icon-button" title="Artifact indir" href={`/api/releases/${selected.id}/sources/${source.source_id}/artifact`} download><Download size={17} /></a>
                  )}
                </div>
              ))}
            </div>
          </section>

          {selected.status === "frozen" && (
            <section className="release-section">
              <h3><FileArchive size={16} /> Kanonik exportlar</h3>
              <div className="release-export-list">
                {(["jsonl", "txt"] as const).map((format) => {
                  const currentExport = selected.exports.find((item) => item.format === format);
                  const Icon = format === "jsonl" ? FileJson : FileText;
                  const busy = exporting === format || currentExport?.status === "queued" || currentExport?.status === "building";
                  return (
                    <div key={format} className="release-export-row">
                      <Icon size={18} aria-hidden="true" />
                      <div>
                        <strong>{format.toUpperCase()}</strong>
                        <span>{exportStatusText(currentExport)}</span>
                        {currentExport?.object_sha256 && <code>{currentExport.object_sha256}</code>}
                      </div>
                      <div className="release-export-actions">
                        {currentExport?.status === "ready" && canDownload && (
                          <>
                            <a className="icon-button" title={`${format.toUpperCase()} indir`} href={`/api/releases/${selected.id}/exports/${format}/artifact`} download><Download size={16} /></a>
                            <a className="icon-button" title="Export manifestini indir" href={`/api/releases/${selected.id}/exports/${format}/manifest`} download><ShieldCheck size={16} /></a>
                          </>
                        )}
                        {currentExport?.status !== "ready" && canManage && (
                          <button className="icon-button" type="button" disabled={busy} title={`${format.toUpperCase()} export üret`} onClick={() => void createExport(selected, format)}>
                            {busy ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {selected.status === "frozen" && selected.manifest_sha256 && (
            <section className="release-section manifest-section">
              <h3><Check size={16} /> Manifest</h3>
              <code>{selected.manifest_sha256}</code>
              {canDownload && <a className="secondary-button" href={`/api/releases/${selected.id}/manifest`} download><Download size={17} />Manifest indir</a>}
            </section>
          )}
        </aside>
      )}

      <dialog ref={createDialog} className="source-dialog release-dialog">
        <form onSubmit={createRelease}>
          <div className="dialog-header">
            <div><span>Release Builder</span><h2>Yeni release</h2></div>
            <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => createDialog.current?.close()}><X size={19} /></button>
          </div>
          <div className="form-grid">
            <label>Ad<input name="name" maxLength={120} placeholder="Türkçe instruction" required /></label>
            <label>Sürüm<input name="version" maxLength={80} placeholder="v1" required /></label>
            <label className="full-width">İçerik amacı<select value={purpose} onChange={(event) => { setPurpose(event.target.value); setSelectedSourceIDs(new Set()); }}>{purposes.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          </div>
          <fieldset className="release-source-picker">
            <legend>Onaylı kaynaklar</legend>
            {eligibleSources.map((source) => (
              <label key={source.id}>
                <input type="checkbox" checked={selectedSourceIDs.has(source.id)} onChange={(event) => toggleSource(source.id, event.target.checked)} />
                <span><strong>{source.name}</strong><small>{source.language} · {source.domain} · {source.sampled_document_count} örnek</small></span>
              </label>
            ))}
            {eligibleSources.length === 0 && <p className="muted-copy">Bu amaç için onaylı kaynak bulunmuyor.</p>}
          </fieldset>
          <div className="dialog-actions"><button className="text-button" type="button" onClick={() => createDialog.current?.close()}>İptal</button><button className="primary-button" type="submit" disabled={selectedSourceIDs.size === 0}>Draft oluştur</button></div>
        </form>
      </dialog>
    </section>
  );
}

function ReleaseStatus({ value }: { value: Release["status"] }) {
  return <span className={`release-status ${value}`}>{releaseStatusLabel(value)}</span>;
}

function releaseStatusLabel(value: Release["status"]) {
  return value === "frozen" ? "Frozen" : value === "draft" ? "Draft" : "Superseded";
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function gateRows(release: Release) {
  const definitions = [
    ["source_gate", "Kaynak snapshot'ı"],
    ["rights_gate", "Haklar"],
    ["pii_gate", "PII"],
    ["exact_duplicate_gate", "Exact tekrar"],
    ["normalized_dedup_gate", "Normalize dedup"],
    ["near_duplicate_report", "Yakın tekrarlar"],
    ["document_review_gate", "Belge incelemesi"],
    ["decontamination", "Dekontaminasyon"],
    ["approximate_decontamination", "Yaklaşık sızıntı"],
  ] as const;
  return definitions.map(([key, label]) => {
    const value = release.gate_results?.[key];
    const status = value && typeof value === "object" && "status" in value ? String(value.status) : "pending";
    if (key === "near_duplicate_report" && (!value || typeof value !== "object")) {
      return { label, status: "not_applicable", text: "Legacy" };
    }
    if (key === "near_duplicate_report" && value && typeof value === "object") {
      if (status === "inconclusive") return { label, status: "warning", text: "Belirsiz" };
      const count = "potential_pair_count" in value ? Number(value.potential_pair_count) : 0;
      return {
        label,
        status: count > 0 ? "warning" : "passed",
        text: count > 0 ? `${count.toLocaleString("tr-TR")} çift` : "Aday yok",
      };
    }
    if (key === "approximate_decontamination" && (!value || typeof value !== "object")) {
      return { label, status: "not_applicable", text: "Legacy" };
    }
    if (key === "approximate_decontamination" && value && typeof value === "object") {
      if (status === "not_applicable") return { label, status, text: "Uygulanmaz" };
      if (status === "inconclusive") return { label, status: "warning", text: "Belirsiz" };
      const count = "potential_match_count" in value ? Number(value.potential_match_count) : 0;
      return {
        label,
        status: count > 0 ? "warning" : "passed",
        text: count > 0 ? `${count.toLocaleString("tr-TR")} aday` : "Aday yok",
      };
    }
    const text = status === "passed" ? "Geçti" : status === "blocked" || status === "failed" ? "Bloke" : status === "not_applicable" ? "Uygulanmaz" : "Bekliyor";
    return { label, status, text };
  });
}

type MixtureEntry = {
  value: string;
  source_count: number;
  source_share_bps: number;
  byte_size: number;
  byte_share_bps: number;
  line_count: number;
  line_share_bps: number;
};

type NearDuplicateReport = {
  schema_version: "derlem.release-near-dedup-report.v1";
  status: "reported" | "inconclusive";
  indexed_document_count: number;
  potential_pair_count: number;
  within_source_pair_count: number;
  cross_source_pair_count: number;
  candidate_overflow_document_count: number;
  hamming_threshold: number;
  sample_pairs: Array<{
    source_sha256: string;
    source_ordinal: number;
    matched_source_sha256: string;
    matched_source_ordinal: number;
    relation: "within_source" | "cross_source";
    hamming_distance: number;
    similarity_estimate_bps: number;
  }>;
};

function nearDuplicateReport(release: Release): NearDuplicateReport | undefined {
  const candidate = release.gate_results?.near_duplicate_report;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return undefined;
  const report = candidate as Partial<NearDuplicateReport>;
  if (report.schema_version !== "derlem.release-near-dedup-report.v1") return undefined;
  return report as NearDuplicateReport;
}

function releaseSourceLabel(release: Release, sha256: string) {
  return release.sources.find((source) => source.source_sha256 === sha256)?.source_name
    ?? sha256.slice(0, 10);
}

type MixtureReport = {
  schema_version: "derlem.mixture-report.v1" | "derlem.mixture-report.v2";
  totals: { source_count: number; byte_size: number; line_count: number };
  dimensions: Record<"language" | "domain" | "source_type" | "license" | "rights_status", MixtureEntry[]>;
  quality?: QualityMixture;
};

type QualityBand = {
  band: "low" | "medium" | "high";
  score_min: number;
  score_max: number;
  document_count: number;
  document_share_bps: number;
};

type QualityDimension = {
  score_sum: number;
  average_score_milli: number | null;
  bands: QualityBand[];
};

type QualityMixture = {
  schema_version: "derlem.quality-mixture.v1" | "derlem.quality-mixture.v2";
  coverage_status: "complete" | "partial" | "unavailable";
  sample_document_count: number;
  scored_document_count: number;
  coverage_bps: number;
  legacy_document_count: number;
  missing_review_document_count: number;
  dimensions: Record<"overall" | "language" | "coherence" | "information_density" | "cleanliness", QualityDimension>;
};

function mixtureReport(release: Release): MixtureReport | undefined {
  const candidate = release.gate_results?.mixture_report;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return undefined;
  const report = candidate as Partial<MixtureReport>;
  if (!["derlem.mixture-report.v1", "derlem.mixture-report.v2"].includes(report.schema_version ?? "") || !report.totals || !report.dimensions) return undefined;
  return report as MixtureReport;
}

function MixtureDimension({ label, entries }: { label: string; entries: MixtureEntry[] }) {
  return (
    <div className="mixture-dimension">
      <strong>{label}</strong>
      <div>
        {entries.map((entry) => {
          const share = entry.byte_size > 0 ? entry.byte_share_bps : entry.source_share_bps;
          return (
            <div key={entry.value}>
              <span title={entry.value}>{entry.value}</span>
              <b>{formatBasisPoints(share)} · {entry.source_count.toLocaleString("tr-TR")}</b>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function QualityMixtureSummary({ quality }: { quality: QualityMixture }) {
  const dimensions: Array<[keyof QualityMixture["dimensions"], string]> = [
    ["overall", "Genel"],
    ["language", "Dil"],
    ["coherence", "Tutarlılık"],
    ["information_density", "Bilgi"],
    ["cleanliness", "Temizlik"],
  ];
  return (
    <div className="quality-mixture">
      <div className="quality-mixture-header">
        <strong>Kalite örneklemi</strong>
        <span>{quality.scored_document_count.toLocaleString("tr-TR")} / {quality.sample_document_count.toLocaleString("tr-TR")} · {formatBasisPoints(quality.coverage_bps)}</span>
      </div>
      <div className="quality-band-legend" aria-label="Kalite bantları">
        <span className="low">Düşük 1-2</span><span className="medium">Orta 3</span><span className="high">Yüksek 4-5</span>
      </div>
      <div className="quality-dimensions">
        {dimensions.map(([key, label]) => {
          const dimension = quality.dimensions[key];
          return (
            <div className="quality-dimension-row" key={key}>
              <span>{label}</span>
              <div className="quality-band-bar" role="img" aria-label={`${label} kalite bantları`}>
                {dimension.bands.map((band) => (
                  <i
                    className={band.band}
                    key={band.band}
                    style={{ width: `${band.document_share_bps / 100}%` }}
                    title={`${band.document_count.toLocaleString("tr-TR")} belge · ${formatBasisPoints(band.document_share_bps)}`}
                  />
                ))}
              </div>
              <b>{dimension.average_score_milli === null ? "-" : (dimension.average_score_milli / 1000).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}</b>
            </div>
          );
        })}
      </div>
      {(quality.legacy_document_count > 0 || quality.missing_review_document_count > 0) && (
        <small>Legacy {quality.legacy_document_count.toLocaleString("tr-TR")} · Eksik {quality.missing_review_document_count.toLocaleString("tr-TR")}</small>
      )}
    </div>
  );
}

function formatBasisPoints(value: number) {
  return `${(value / 100).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}%`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function exportStatusText(value: Release["exports"][number] | undefined) {
  if (!value) return "Henüz üretilmedi";
  if (value.status === "ready") {
    const records = value.record_count?.toLocaleString("tr-TR") ?? "0";
    const tokens = value.estimated_token_count;
    const tokenSummary = tokens === undefined ? "" : ` · ~${formatCount(tokens)} token`;
    return `${records} kayıt · ${formatBytes(value.byte_size ?? 0)}${tokenSummary}`;
  }
  if (value.status === "failed") return "Başarısız · yeniden denenebilir";
  return value.status === "building" ? "Üretiliyor" : "Kuyrukta";
}

function formatCount(value: number) {
  return new Intl.NumberFormat("tr-TR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
