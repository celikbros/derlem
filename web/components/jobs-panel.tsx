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
  freeze_release: "Release freeze",
};

export function JobsPanel({ onNotice }: { onNotice: (message: string) => void }) {
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
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
                <td><strong>{jobLabels[job.job_type] ?? job.job_type}</strong><small className="row-subtitle">{job.id.slice(0, 8)}</small></td>
                <td><JobStatus status={job.status} /></td>
                <td>{job.attempts} / {job.max_attempts}</td>
                <td>{formatDate(job.created_at)}</td>
                <td className={job.last_error ? "error-text" : undefined}>{job.last_error ?? resultSummary(job)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && jobs.length === 0 && <div className="empty-state"><Clock3 size={24} /><p>Henüz iş kaydı yok.</p></div>}
      </div>
    </section>
  );
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
  return job.status === "succeeded" ? "Başarılı" : "-";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
