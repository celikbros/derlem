"use client";

import { AlertCircle, CheckCircle2, Clock3, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { messageFrom, requestJSON } from "@/lib/client-api";
import type { BackgroundJob } from "@/lib/types";

const jobLabels: Record<string, string> = {
  ingest_local_file: "Dosya içe aktarma",
  ingest_staged_file: "Tarayıcı yüklemesi",
  scan_pii: "PII taraması",
  check_exact_duplicate: "Dosya dedup",
  index_document_fingerprints: "Normalize dedup",
  sample_documents: "Belge örnekleme",
  resample_documents: "Belge yeniden örnekleme",
  freeze_release: "Release freeze",
  export_release: "Release export",
};

export function JobsPanel({ onNotice }: { onNotice: (message: string) => void }) {
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const payload = await requestJSON<{ items: BackgroundJob[] }>("/api/jobs?limit=200");
      setJobs(payload.items);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice]);

  useEffect(() => { void load(); }, [load]);
  const hasActiveJobs = jobs.some((job) => job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = window.setInterval(() => { void load(true); }, 2_000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, load]);

  return (
    <section className="jobs-panel">
      <div className="table-toolbar">
        <div className="toolbar-title">
          <span>{jobs.length.toLocaleString("tr-TR")} iş</span>
          <small>Kuyruk ve worker sonuçları</small>
        </div>
        <button className="icon-button" type="button" title="İşleri yenile" onClick={() => void load()}>
          <RefreshCw className={loading ? "spin" : ""} size={18} aria-hidden="true" />
        </button>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>İş</th><th>Durum</th><th>Deneme</th><th>Oluşturulma</th><th>Sonuç</th></tr></thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>
                  <strong>{jobLabels[job.job_type] ?? job.job_type}</strong>
                  <small className="row-subtitle">{job.id.slice(0, 8)}</small>
                  {job.status === "running" && jobProgress(job) && <div className="job-progress-mobile"><JobResult job={job} /></div>}
                </td>
                <td><JobStatus status={job.status} /></td>
                <td>{job.attempts} / {job.max_attempts}</td>
                <td>{formatDate(job.created_at)}</td>
                <td className={job.last_error ? "error-text" : undefined}>
                  {job.last_error ?? <JobResult job={job} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && jobs.length === 0 && <div className="empty-state"><Clock3 size={24} /><p>Henüz iş kaydı yok.</p></div>}
      </div>
    </section>
  );
}

type Progress = Record<string, unknown>;

const phaseLabels: Record<string, string> = {
  ingesting: "Dosya kopyalanıyor",
  scanning_pii: "PII taranıyor",
  fingerprinting: "Parmak izi çıkarılıyor",
  matching_duplicates: "Tekrarlar karşılaştırılıyor",
  sampling: "Örnek seçiliyor",
  publishing_samples: "Örnekler yayınlanıyor",
  building: "Export oluşturuluyor",
};

function JobResult({ job }: { job: BackgroundJob }) {
  const progress = jobProgress(job);
  if (job.status !== "running" || !progress) return resultSummary(job);

  const processedBytes = numberFrom(progress, "input_bytes_processed");
  const totalBytes = numberFrom(progress, "input_bytes_total");
  const percent = totalBytes > 0 ? Math.min(100, (processedBytes / totalBytes) * 100) : undefined;
  const phase = typeof job.result?.phase === "string" ? job.result.phase : "running";
  const detail = progressDetail(job.job_type, progress, processedBytes, totalBytes);

  return (
    <div className="job-progress-cell">
      <div><strong>{phaseLabels[phase] ?? "İşleniyor"}</strong>{percent !== undefined && <span>%{percent.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}</span>}</div>
      <small>{detail}</small>
      {percent !== undefined && <progress max={100} value={percent} aria-label={`İş ilerlemesi yüzde ${percent.toFixed(1)}`} />}
    </div>
  );
}

function jobProgress(job: BackgroundJob): Progress | undefined {
  const progress = job.result?.progress;
  return progress && typeof progress === "object" && !Array.isArray(progress)
    ? progress as Progress
    : undefined;
}

function progressDetail(jobType: string, progress: Progress, processedBytes: number, totalBytes: number) {
  const lines = numberFrom(progress, "lines_read").toLocaleString("tr-TR");
  const byteSummary = totalBytes > 0 ? `${formatBytes(processedBytes)} / ${formatBytes(totalBytes)}` : formatBytes(processedBytes);
  if (jobType === "index_document_fingerprints") {
    return `${byteSummary} · ${lines} satır · ${numberFrom(progress, "indexed_documents").toLocaleString("tr-TR")} indeks`;
  }
  if (["sample_documents", "resample_documents"].includes(jobType)) {
    return `${byteSummary} · ${numberFrom(progress, "documents_scanned").toLocaleString("tr-TR")} belge · ${numberFrom(progress, "risk_candidate_documents").toLocaleString("tr-TR")} risk adayı`;
  }
  if (jobType === "scan_pii") {
    return `${byteSummary} · ${lines} satır · ${numberFrom(progress, "findings_count").toLocaleString("tr-TR")} bulgu`;
  }
  if (jobType === "export_release") {
    return `${byteSummary} · ${numberFrom(progress, "records_written").toLocaleString("tr-TR")} kayıt`;
  }
  return `${byteSummary} · ${lines} satır`;
}

function numberFrom(value: Progress, key: string) {
  const candidate = value[key];
  return typeof candidate === "number" && Number.isFinite(candidate) ? candidate : 0;
}

export function JobStatus({ status }: { status: BackgroundJob["status"] }) {
  const icons = {
    queued: <Clock3 size={14} />,
    running: <LoaderCircle className="spin" size={14} />,
    succeeded: <CheckCircle2 size={14} />,
    failed: <AlertCircle size={14} />,
    cancelled: <AlertCircle size={14} />,
  };
  const labels = { queued: "Kuyrukta", running: "Çalışıyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "İptal" };
  return <span className={`job-status ${status}`}>{icons[status]}{labels[status]}</span>;
}

function resultSummary(job: BackgroundJob) {
  if (job.status === "queued") return "Bekliyor";
  if (job.status === "running") return "İşleniyor";
  if (job.job_type === "scan_pii" && typeof job.result?.status === "string") return `PII: ${job.result.status}`;
  if (job.job_type === "index_document_fingerprints" && typeof job.result?.status === "string") return `Dedup: ${job.result.status}`;
  if (["sample_documents", "resample_documents"].includes(job.job_type) && job.status === "succeeded") {
    const samples = Number(job.result?.sample_size ?? 0).toLocaleString("tr-TR");
    const risky = Number(job.result?.selected_risk_documents ?? 0).toLocaleString("tr-TR");
    return `${samples} örnek · ${risky} riskli`;
  }
  if (job.job_type === "export_release" && job.status === "succeeded") {
    const records = Number(job.result?.record_count ?? 0).toLocaleString("tr-TR");
    return `${String(job.result?.format ?? "").toUpperCase()} · ${records} kayıt`;
  }
  return job.status === "succeeded" ? "Başarılı" : "-";
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes.toLocaleString("tr-TR")} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} ${unit}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
