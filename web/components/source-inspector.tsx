"use client";

import {
  Check,
  CheckCircle2,
  Edit3,
  History,
  LoaderCircle,
  RefreshCw,
  ScanLine,
  ShieldAlert,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { JobStatus } from "@/components/jobs-panel";
import { messageFrom, requestJSON } from "@/lib/client-api";
import type { BackgroundJob, PIIScan, Review, Source, User } from "@/lib/types";

const purposeLabels: Record<string, string> = {
  pretrain: "Pretrain",
  instruction: "Instruction",
  preference: "Preference",
  eval: "Eval",
  holdout: "Holdout",
  post_training: "Post-training",
};

const findingLabels: Record<string, string> = {
  tckn: "TCKN",
  iban: "IBAN",
  email: "E-posta",
  phone: "Telefon",
  payment_card: "Ödeme kartı",
};

export function SourceInspector({
  source,
  user,
  onClose,
  onChanged,
  onRefresh,
  onNotice,
}: {
  source: Source;
  user: User;
  onClose: () => void;
  onChanged: (source: Source) => void;
  onRefresh: () => Promise<void>;
  onNotice: (message: string) => void;
}) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [scans, setScans] = useState<PIIScan[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const editDialog = useRef<HTMLDialogElement>(null);

  const loadActivity = useCallback(async () => {
    setLoading(true);
    try {
      const [reviewPayload, scanPayload, jobPayload] = await Promise.all([
        requestJSON<{ items: Review[] }>(`/api/sources/${source.id}/reviews`),
        requestJSON<{ items: PIIScan[] }>(`/api/sources/${source.id}/pii-scans`),
        requestJSON<{ items: BackgroundJob[] }>(`/api/jobs?source_id=${source.id}&limit=20`),
      ]);
      setReviews(reviewPayload.items);
      setScans(scanPayload.items);
      setJobs(jobPayload.items);
      const ingestFinished = jobPayload.items.some((job) => ["ingest_local_file", "ingest_staged_file"].includes(job.job_type) && job.status === "succeeded");
      const scanFinished = jobPayload.items.some((job) => job.job_type === "scan_pii" && job.status === "succeeded");
      if ((!source.object_sha256 && ingestFinished) || (source.pii_status === "not_scanned" && scanFinished)) {
        await onRefresh();
      }
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice, onRefresh, source.id, source.object_sha256, source.pii_status]);

  useEffect(() => { void loadActivity(); }, [loadActivity, source.version]);
  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setTimeout(() => { void loadActivity(); }, 1500);
    return () => window.clearTimeout(timer);
  }, [jobs, loadActivity]);

  const canReview = user.roles.some((role) => ["admin", "moderator", "expert_reviewer"].includes(role));
  const gateChecks = [
    { label: "Dosya alındı", passed: Boolean(source.object_sha256) },
    { label: "Haklar temiz", passed: source.rights_status === "cleared" },
    { label: "Lisans kanıtı", passed: Boolean(source.license_evidence_ref) },
    { label: "PII temiz", passed: source.pii_status === "clear" },
  ];
  const approvalReady = gateChecks.every((gate) => gate.passed) && source.approval_status !== "approved_source";
  const latestScan = scans[0];

  async function updateSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = { ...Object.fromEntries(new FormData(form).entries()), version: source.version };
    try {
      const updated = await requestJSON<Source>(`/api/sources/${source.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      editDialog.current?.close();
      onChanged(updated);
      onNotice("Kaynak metadata’sı güncellendi.");
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    if (!(file instanceof File) || file.size === 0) {
      onNotice("Yüklenecek dosyayı seçin.");
      return;
    }
    setUploading(true);
    try {
      const payload = new FormData();
      payload.set("file", file, file.name);
      const result = await requestJSON<{ job_id: string }>(`/api/sources/${source.id}/upload`, {
        method: "POST",
        body: payload,
      });
      form.reset();
      onNotice(`Dosya yüklendi ve kuyruğa alındı: ${result.job_id.slice(0, 8)}`);
      await loadActivity();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setUploading(false);
    }
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (!decision) return;
    const form = event.currentTarget;
    const reason = String(new FormData(form).get("reason") ?? "").trim();
    if (decision !== "approved" && !reason) {
      onNotice("Ret veya hassas inceleme kararında gerekçe zorunludur.");
      return;
    }
    try {
      const payload = await requestJSON<{ source: Source; review: Review }>(`/api/sources/${source.id}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason: reason || null }),
      });
      form.reset();
      onChanged(payload.source);
      onNotice("İnceleme kararı kaydedildi.");
      await loadActivity();
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }

  return (
    <aside className="inspector" aria-label="Kaynak ayrıntısı">
      <div className="inspector-header">
        <div><span>Kaynak ayrıntısı</span><h2>{source.name}</h2></div>
        <div className="header-actions">
          <button className="icon-button" type="button" title="Metadata düzenle" onClick={() => editDialog.current?.showModal()}><Edit3 size={17} /></button>
          <button className="icon-button" type="button" title="Ayrıntıyı kapat" onClick={onClose}><X size={18} /></button>
        </div>
      </div>

      <dl>
        <Detail label="Amaç" value={purposeLabels[source.content_purpose]} />
        <Detail label="Kaynak tipi" value={source.source_type} />
        <Detail label="Lisans" value={source.license} />
        <Detail label="Hak durumu" value={source.rights_status} />
        <Detail label="Dil / alan" value={`${source.language} / ${source.domain}`} />
        <Detail label="Köken" value={source.lineage_ref} mono />
        <Detail label="Durum" value={source.approval_status} />
        <Detail label="PII / risk" value={`${source.pii_status} / ${source.risk_level}`} />
        {source.declared_sha256 && <Detail label="Beyan SHA256" value={source.declared_sha256} mono />}
        {source.declared_byte_size !== undefined && <Detail label="Beyan boyutu" value={formatBytes(source.declared_byte_size)} />}
        {source.declared_line_count !== undefined && <Detail label="Beyan satırı" value={source.declared_line_count.toLocaleString("tr-TR")} />}
        {source.object_sha256 && <Detail label="SHA256" value={source.object_sha256} mono />}
        {source.byte_size !== undefined && <Detail label="Boyut" value={formatBytes(source.byte_size)} />}
        {source.line_count !== undefined && <Detail label="Satır" value={source.line_count.toLocaleString("tr-TR")} />}
      </dl>

      {!source.object_sha256 && (
        <section className="inspector-section">
          <h3><Upload size={16} /> Dosya</h3>
          <form className="ingest-form" onSubmit={uploadFile}>
            <label>Dosya<input name="file" type="file" accept=".txt,.jsonl,.json,.csv,.tsv,text/plain,application/json" required /></label>
            <button className="secondary-button" type="submit" disabled={uploading}>
              {uploading ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
              {uploading ? "Yükleniyor" : "Dosyayı yükle"}
            </button>
          </form>
        </section>
      )}

      <section className="inspector-section">
        <div className="section-heading">
          <h3><ShieldAlert size={16} /> Onay kapısı</h3>
          <button className="icon-button compact" type="button" title="Ayrıntıları yenile" onClick={() => void loadActivity()}>
            <RefreshCw className={loading ? "spin" : ""} size={15} />
          </button>
        </div>
        <ul className="gate-list">
          {gateChecks.map((gate) => <li key={gate.label} className={gate.passed ? "passed" : "blocked"}>{gate.passed ? <Check size={14} /> : <X size={14} />}{gate.label}</li>)}
        </ul>
        {latestScan && (
          <div className="scan-summary">
            <span><ScanLine size={14} /> {latestScan.scanner_version}</span>
            <small>{findingSummary(latestScan)}</small>
          </div>
        )}
      </section>

      {canReview && (
        <section className="inspector-section">
          <h3><CheckCircle2 size={16} /> Moderasyon</h3>
          <form className="review-form" onSubmit={submitReview}>
            <label>Karar gerekçesi<textarea name="reason" rows={3} placeholder="Ret ve hassas incelemede zorunlu" /></label>
            <div className="review-actions">
              <button className="approve-button" type="submit" name="decision" value="approved" disabled={!approvalReady} title={approvalReady ? "Kaynağı onayla" : "Onay kapıları tamamlanmadı"}><Check size={16} />Onayla</button>
              <button className="warning-button" type="submit" name="decision" value="sensitive_review"><ShieldAlert size={16} />Hassas</button>
              <button className="danger-button" type="submit" name="decision" value="rejected"><XCircle size={16} />Reddet</button>
            </div>
          </form>
        </section>
      )}

      <section className="inspector-section">
        <h3><History size={16} /> Geçmiş</h3>
        <div className="activity-list">
          {jobs.slice(0, 3).map((job) => <div key={job.id}><JobStatus status={job.status} /><span>{job.job_type}</span><small>{formatDate(job.created_at)}</small></div>)}
          {reviews.slice(0, 3).map((review) => <div key={review.id}><span className={`review-decision ${review.decision}`}>{review.decision}</span><span>{review.reason ?? "Gerekçe yok"}</span><small>{formatDate(review.created_at)}</small></div>)}
          {!loading && jobs.length === 0 && reviews.length === 0 && <p className="muted-copy">Henüz işlem geçmişi yok.</p>}
        </div>
      </section>

      <dialog ref={editDialog} className="source-dialog" key={`${source.id}-${source.version}`}>
        <form onSubmit={updateSource}>
          <div className="dialog-header">
            <div><span>Kaynak sürümü {source.version}</span><h2>Metadata düzenle</h2></div>
            <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => editDialog.current?.close()}><X size={19} /></button>
          </div>
          <div className="form-grid">
            <label className="full-width">Kaynak adı<input name="name" defaultValue={source.name} required maxLength={240} /></label>
            <label>Kaynak tipi<input name="source_type" defaultValue={source.source_type} required /></label>
            <label>İçerik amacı<input value={purposeLabels[source.content_purpose]} disabled /></label>
            <label>Lisans<input name="license" defaultValue={source.license} required /></label>
            <label>Hak durumu<select name="rights_status" defaultValue={source.rights_status}><option value="unknown">Bilinmiyor</option><option value="cleared">Temizlendi</option><option value="restricted">Kısıtlı</option><option value="blocked">Engelli</option></select></label>
            <label>Dil<input name="language" defaultValue={source.language} required /></label>
            <label>Alan<input name="domain" defaultValue={source.domain} required /></label>
            <label className="full-width">Kaynak URL’si<input name="source_url" type="url" defaultValue={source.source_url ?? ""} /></label>
            <label className="full-width">Lisans kanıtı<input name="license_evidence_ref" defaultValue={source.license_evidence_ref ?? ""} /></label>
            <label className="full-width">Köken bilgisi<input name="lineage_ref" defaultValue={source.lineage_ref} required /></label>
          </div>
          <div className="dialog-actions"><button className="text-button" type="button" onClick={() => editDialog.current?.close()}>İptal</button><button className="primary-button" type="submit">Değişiklikleri kaydet</button></div>
        </form>
      </dialog>
    </aside>
  );
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt>{label}</dt><dd className={mono ? "mono" : undefined}>{value}</dd></div>;
}

function findingSummary(scan: PIIScan) {
  const findings = Object.entries(scan.findings).filter(([, count]) => count > 0);
  if (findings.length === 0) return "Bulgu yok";
  return findings.map(([type, count]) => `${findingLabels[type] ?? type}: ${count}`).join(" · ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value / 1024;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} ${units[index]}`;
}
