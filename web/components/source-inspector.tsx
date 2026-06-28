"use client";

import {
  Check,
  CheckCircle2,
  ClipboardCheck,
  Edit3,
  FileText,
  History,
  LoaderCircle,
  RefreshCw,
  Scale,
  ScanLine,
  Save,
  ShieldAlert,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { JobStatus } from "@/components/jobs-panel";
import { messageFrom, requestJSON } from "@/lib/client-api";
import type { BackgroundJob, Document, DocumentQualitySummary, DocumentReview, DocumentSampleGeneration, PIIScan, Review, Source, User } from "@/lib/types";

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

const riskReasonLabels: Record<string, string> = {
  short_text: "Çok kısa",
  long_text: "Çok uzun",
  control_characters: "Kontrol karakteri",
  high_symbol_ratio: "Aşırı sembol",
  repeated_character_run: "Karakter tekrarı",
  low_lexical_diversity: "Düşük kelime çeşitliliği",
  identifier_pattern: "Kimlik/iletişim kalıbı",
  malformed_json: "Bozuk JSON",
  missing_text_field: "Metin alanı eksik",
};

const qualityScoreFields = [
  { name: "quality_score", label: "Genel", title: "Belgenin bütünsel eğitim değeri" },
  { name: "language_quality_score", label: "Dil", title: "Dil doğruluğu ve doğallığı" },
  { name: "coherence_score", label: "Tutarlılık", title: "Metnin kendi içindeki anlam ve akış tutarlılığı" },
  { name: "information_density_score", label: "Bilgi", title: "Yararlı bilgi ve içerik yoğunluğu" },
  { name: "cleanliness_score", label: "Temizlik", title: "Gürültüden ve biçim bozukluklarından arınmışlık" },
] as const;

type QualityScoreName = typeof qualityScoreFields[number]["name"];
type QualityScores = Record<QualityScoreName, number>;

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
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentStatusFilter, setDocumentStatusFilter] = useState<"pending" | "risk" | "approved" | "flagged" | "all">("pending");
  const [activeDocument, setActiveDocument] = useState<Document | null>(null);
  const [documentReviews, setDocumentReviews] = useState<DocumentReview[]>([]);
  const [qualitySummary, setQualitySummary] = useState<DocumentQualitySummary | null>(null);
  const [sampleGenerations, setSampleGenerations] = useState<DocumentSampleGeneration[]>([]);
  const [documentContent, setDocumentContent] = useState("");
  const [selectedDocumentIDs, setSelectedDocumentIDs] = useState<Set<string>>(new Set());
  const [bulkReviewing, setBulkReviewing] = useState(false);
  const [resampling, setResampling] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const editDialog = useRef<HTMLDialogElement>(null);
  const documentDialog = useRef<HTMLDialogElement>(null);

  const loadActivity = useCallback(async () => {
    setLoading(true);
    try {
      const [reviewPayload, scanPayload, jobPayload, documentPayload, generationPayload, qualityPayload] = await Promise.all([
        requestJSON<{ items: Review[] }>(`/api/sources/${source.id}/reviews`),
        requestJSON<{ items: PIIScan[] }>(`/api/sources/${source.id}/pii-scans`),
        requestJSON<{ items: BackgroundJob[] }>(`/api/jobs?source_id=${source.id}&limit=20`),
        requestJSON<{ items: Document[] }>(`/api/sources/${source.id}/documents?limit=200`),
        requestJSON<{ items: DocumentSampleGeneration[] }>(`/api/sources/${source.id}/document-sample-generations`),
        requestJSON<DocumentQualitySummary>(`/api/sources/${source.id}/document-quality-summary`),
      ]);
      setReviews(reviewPayload.items);
      setScans(scanPayload.items);
      setJobs(jobPayload.items);
      setDocuments(documentPayload.items);
      setSampleGenerations(generationPayload.items);
      setQualitySummary(qualityPayload);
      const pendingIDs = new Set(documentPayload.items
        .filter((document) => document.status === "sampled" || document.status === "edited")
        .map((document) => document.id));
      setSelectedDocumentIDs((current) => new Set([...current].filter((id) => pendingIDs.has(id))));
      const ingestFinished = jobPayload.items.some((job) => ["ingest_local_file", "ingest_staged_file"].includes(job.job_type) && job.status === "succeeded");
      const scanFinished = jobPayload.items.some((job) => job.job_type === "scan_pii" && job.status === "succeeded");
      const duplicateCheckFinished = jobPayload.items.some((job) => job.job_type === "check_exact_duplicate" && job.status === "succeeded");
      const normalizedDedupFinished = jobPayload.items.some((job) => job.job_type === "index_document_fingerprints" && job.status === "succeeded");
      const samplingFinished = jobPayload.items.some((job) => job.job_type === "sample_documents" && job.status === "succeeded");
      const resamplingFinished = jobPayload.items.some((job) => job.job_type === "resample_documents" && ["succeeded", "failed"].includes(job.status));
      if (
        (!source.object_sha256 && ingestFinished)
        || (source.pii_status === "not_scanned" && scanFinished)
        || (source.duplicate_status === "not_checked" && duplicateCheckFinished)
        || (source.normalized_dedup_status === "not_checked" && normalizedDedupFinished)
        || (source.document_sampling_status === "not_sampled" && samplingFinished)
        || (source.document_sampling_status === "resampling" && resamplingFinished)
      ) {
        await onRefresh();
      }
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice, onRefresh, source.document_sampling_status, source.duplicate_status, source.id, source.normalized_dedup_status, source.object_sha256, source.pii_status]);

  useEffect(() => { void loadActivity(); }, [loadActivity, source.version]);
  useEffect(() => {
    setSelectedDocumentIDs(new Set());
    setQualitySummary(null);
  }, [source.id]);
  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setTimeout(() => { void loadActivity(); }, 1500);
    return () => window.clearTimeout(timer);
  }, [jobs, loadActivity]);

  const canReview = user.roles.some((role) => ["admin", "moderator", "expert_reviewer"].includes(role));
  const canEditDocument = user.roles.some((role) => ["admin", "editor"].includes(role));
  const canManageSource = user.roles.some((role) => ["admin", "data_manager", "editor"].includes(role));
  const canIngestSource = user.roles.some((role) => ["admin", "data_manager"].includes(role));
  const canResample = user.roles.includes("admin")
    && source.document_sampling_status === "sampled"
    && source.sampled_document_count > 0
    && source.reviewed_document_count === 0;
  const gateChecks = [
    { label: "Dosya alındı", passed: Boolean(source.object_sha256) },
    { label: "Haklar temiz", passed: source.rights_status === "cleared" },
    { label: "Lisans kanıtı", passed: Boolean(source.license_evidence_ref) },
    { label: "PII temiz", passed: source.pii_status === "clear" },
    { label: "Exact tekrar yok", passed: source.duplicate_status === "unique" },
    { label: "Normalize tekrar yok", passed: source.normalized_dedup_status === "unique" },
    { label: "Belge örnekleri hazır", passed: source.document_sampling_status === "sampled" },
    {
      label: "Örnekler onaylandı",
      passed: source.sampled_document_count > 0
        && source.reviewed_document_count === source.sampled_document_count
        && source.approved_document_count === source.sampled_document_count
        && source.flagged_document_count === 0,
    },
  ];
  const approvalReady = gateChecks.every((gate) => gate.passed) && source.approval_status !== "approved_source";
  const latestScan = scans[0];
  const pendingDocuments = documents
    .filter((document) => document.status === "sampled" || document.status === "edited")
    .sort((left, right) => right.risk_score - left.risk_score || left.source_ordinal - right.source_ordinal);
  const riskyDocuments = pendingDocuments.filter((document) => document.risk_score > 0);
  const approvedDocuments = documents.filter((document) => document.status === "approved");
  const flaggedDocuments = documents.filter((document) => document.status === "rejected" || document.status === "sensitive_review");
  const filteredDocuments = documentStatusFilter === "pending"
    ? pendingDocuments
    : documentStatusFilter === "risk"
      ? riskyDocuments
    : documentStatusFilter === "approved"
      ? approvedDocuments
      : documentStatusFilter === "flagged"
        ? flaggedDocuments
        : documents;
  const selectableDocuments = documentStatusFilter === "risk" ? riskyDocuments : pendingDocuments;
  const riskSampleCount = documents.filter((document) => document.risk_score > 0).length;
  const reviewedCount = source.reviewed_document_count;
  const sampleCount = source.sampled_document_count;
  const reviewPercent = sampleCount > 0 ? Math.round((reviewedCount / sampleCount) * 100) : 0;
  const corpusByteSize = source.byte_size ?? source.declared_byte_size;
  const corpusLineCount = source.line_count ?? source.declared_line_count;
  const corpusDocumentCount = source.document_count ?? source.line_count ?? source.declared_line_count;
  const normalizedDuplicateText = source.normalized_duplicate_source_count > 0
    ? `${source.normalized_duplicate_count.toLocaleString("tr-TR")} / ${source.normalized_duplicate_source_count.toLocaleString("tr-TR")} kaynak`
    : source.normalized_duplicate_count.toLocaleString("tr-TR");
  const rightsEvidenceReady = source.rights_status === "cleared" && Boolean(source.license_evidence_ref);
  const rightsTone = source.rights_status === "blocked"
    ? "blocked"
    : source.rights_status === "restricted"
      ? "restricted"
      : rightsEvidenceReady
        ? "cleared"
        : "unknown";

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

  async function openDocument(document: Document) {
    setLoading(true);
    try {
      const [payload, reviewPayload] = await Promise.all([
        requestJSON<{ document: Document; content: string }>(`/api/documents/${document.id}`),
        requestJSON<{ items: DocumentReview[] }>(`/api/documents/${document.id}/reviews`),
      ]);
      setActiveDocument(payload.document);
      setDocumentContent(payload.content);
      setDocumentReviews(reviewPayload.items);
      documentDialog.current?.showModal();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }

  async function openNextPendingDocument() {
    const nextDocument = pendingDocuments[0];
    if (!nextDocument) {
      onNotice("İncelenecek bekleyen örnek kalmadı.");
      return;
    }
    await openDocument(nextDocument);
  }

  async function updateDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeDocument) return;
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    try {
      const updated = await requestJSON<Document>(`/api/documents/${activeDocument.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: documentContent,
          version: activeDocument.current_version,
          reason: reason || null,
        }),
      });
      setDocuments((current) => current.map((document) => document.id === updated.id ? updated : document));
      setActiveDocument(updated);
      setDocumentReviews([]);
      documentDialog.current?.close();
      onNotice(`Belge sürüm ${updated.current_version} olarak kaydedildi.`);
      await onRefresh();
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }

  async function submitDocumentReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeDocument) return;
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (!decision) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const reason = String(data.get("reason") ?? "").trim();
    const qualityScores = readQualityScores(data);
    if (!qualityScores) {
      onNotice("Tüm kalite boyutları 1 ile 5 arasında olmalıdır.");
      return;
    }
    if (decision !== "approved" && !reason) {
      onNotice("Ret veya hassas inceleme kararında gerekçe zorunludur.");
      return;
    }
    try {
      const payload = await requestJSON<{ source: Source; document: Document; review: DocumentReview }>(
        `/api/documents/${activeDocument.id}/reviews`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            decision,
            reason: reason || null,
            ...qualityScores,
            document_version: activeDocument.current_version,
          }),
        },
      );
      setActiveDocument(payload.document);
      const updatedDocuments = documents.map((document) => document.id === payload.document.id ? payload.document : document);
      setDocuments(updatedDocuments);
      setSelectedDocumentIDs((current) => {
        const next = new Set(current);
        next.delete(payload.document.id);
        return next;
      });
      setDocumentReviews((current) => [payload.review, ...current]);
      onChanged(payload.source);
      form.reset();
      const nextPending = updatedDocuments.find((document) =>
        document.id !== payload.document.id && (document.status === "sampled" || document.status === "edited")
      );
      if (nextPending) {
        onNotice("Belge inceleme kararı kaydedildi. Sıradaki örnek açılıyor.");
        await openDocument(nextPending);
      } else {
        documentDialog.current?.close();
        onNotice("Belge inceleme kararı kaydedildi. Bekleyen örnek kalmadı.");
      }
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }

  function toggleDocumentSelection(documentID: string, checked: boolean) {
    setSelectedDocumentIDs((current) => {
      const next = new Set(current);
      if (checked) next.add(documentID);
      else next.delete(documentID);
      return next;
    });
  }

  function toggleAllPendingDocuments(checked: boolean) {
    setSelectedDocumentIDs(checked ? new Set(selectableDocuments.map((document) => document.id)) : new Set());
  }

  async function submitBulkDocumentReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (!decision || selectedDocumentIDs.size === 0) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const reason = String(data.get("reason") ?? "").trim();
    const qualityScores = readQualityScores(data);
    if (!qualityScores) {
      onNotice("Tüm kalite boyutları 1 ile 5 arasında olmalıdır.");
      return;
    }
    if (decision !== "approved" && !reason) {
      onNotice("Toplu ret veya hassas inceleme kararında gerekçe zorunludur.");
      return;
    }
    const selectedDocuments = pendingDocuments.filter((document) => selectedDocumentIDs.has(document.id));
    if (selectedDocuments.length !== selectedDocumentIDs.size) {
      onNotice("Seçimlerden biri artık beklemede değil. Listeyi yenileyin.");
      return;
    }

    setBulkReviewing(true);
    try {
      const payload = await requestJSON<{
        source: Source;
        documents: Document[];
        reviews: DocumentReview[];
      }>(`/api/sources/${source.id}/documents/bulk-reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          documents: selectedDocuments.map((document) => ({
            document_id: document.id,
            document_version: document.current_version,
          })),
          decision,
          reason: reason || null,
          ...qualityScores,
        }),
      });
      const updatedByID = new Map(payload.documents.map((document) => [document.id, document]));
      setDocuments((current) => current.map((document) => updatedByID.get(document.id) ?? document));
      setSelectedDocumentIDs(new Set());
      onChanged(payload.source);
      form.reset();
      onNotice(`${payload.documents.length.toLocaleString("tr-TR")} belge için toplu karar kaydedildi.`);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setBulkReviewing(false);
    }
  }

  async function queueDocumentResample() {
    setResampling(true);
    try {
      const result = await requestJSON<{ job_id: string }>(`/api/sources/${source.id}/documents/resample`, {
        method: "POST",
      });
      onNotice(`Risk bazlı yeniden örnekleme kuyruğa alındı: ${result.job_id.slice(0, 8)}`);
      await onRefresh();
      await loadActivity();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setResampling(false);
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
          {canManageSource && <button className="icon-button" type="button" title="Metadata düzenle" onClick={() => editDialog.current?.showModal()}><Edit3 size={17} /></button>}
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
        <Detail label="Exact tekrar" value={source.duplicate_status} />
        {source.duplicate_of_source_id && <Detail label="Kanonik kaynak" value={source.duplicate_of_source_id} mono />}
        <Detail label="Normalize dedup" value={`${source.normalized_dedup_status} / ${source.normalized_duplicate_count}`} />
        {source.normalized_duplicate_source_count > 0 && <Detail label="Tekrar kaynakları" value={source.normalized_duplicate_source_count.toLocaleString("tr-TR")} />}
        <Detail label="Belge örnekleme" value={`${source.document_sampling_status} / ${source.sampled_document_count}`} />
        <Detail label="Örnek nesli" value={`${source.document_sample_generation} / ${source.document_sampling_method}`} />
        <Detail label="Örnek inceleme" value={`${source.approved_document_count} onay · ${source.flagged_document_count} işaretli`} />
        {source.declared_sha256 && <Detail label="Beyan SHA256" value={source.declared_sha256} mono />}
        {source.declared_byte_size !== undefined && <Detail label="Beyan boyutu" value={formatBytes(source.declared_byte_size)} />}
        {source.declared_line_count !== undefined && <Detail label="Beyan satırı" value={source.declared_line_count.toLocaleString("tr-TR")} />}
        {source.object_sha256 && <Detail label="SHA256" value={source.object_sha256} mono />}
        {source.byte_size !== undefined && <Detail label="Boyut" value={formatBytes(source.byte_size)} />}
        {source.line_count !== undefined && <Detail label="Satır" value={source.line_count.toLocaleString("tr-TR")} />}
      </dl>

      <section className="inspector-section">
        <h3><FileText size={16} /> Corpus özeti</h3>
        <div className="corpus-summary-grid">
          <CorpusMetric label="Boyut" value={corpusByteSize !== undefined ? formatBytes(corpusByteSize) : "Bilinmiyor"} />
          <CorpusMetric label="Satır" value={corpusLineCount !== undefined ? corpusLineCount.toLocaleString("tr-TR") : "Bilinmiyor"} />
          <CorpusMetric label="Doküman" value={corpusDocumentCount !== undefined ? corpusDocumentCount.toLocaleString("tr-TR") : "Bilinmiyor"} />
          <CorpusMetric label="Örnek" value={`${reviewedCount.toLocaleString("tr-TR")} / ${sampleCount.toLocaleString("tr-TR")}`} tone={reviewPercent === 100 ? "good" : "watch"} />
          <CorpusMetric label="Örnek nesli" value={String(source.document_sample_generation)} />
          <CorpusMetric label="Riskli örnek" value={riskSampleCount.toLocaleString("tr-TR")} tone={riskSampleCount > 0 ? "watch" : "good"} />
          <CorpusMetric label="PII" value={source.pii_status} tone={source.pii_status === "clear" ? "good" : "risk"} />
          <CorpusMetric label="Normalize tekrar" value={normalizedDuplicateText} tone={source.normalized_dedup_status === "unique" ? "good" : "risk"} />
        </div>
        {source.object_sha256 && (
          <div className="corpus-hash-row">
            <span>SHA256</span>
            <code>{source.object_sha256}</code>
          </div>
        )}
      </section>

      {canIngestSource && !source.object_sha256 && (
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
          <h3><Scale size={16} /> Hak ve lisans</h3>
          {canManageSource && (
            <button className="icon-button compact" type="button" title="Hak bilgisini düzenle" onClick={() => editDialog.current?.showModal()}>
              <Edit3 size={15} />
            </button>
          )}
        </div>
        <div className={`rights-evidence-card ${rightsTone}`}>
          <div>
            <span>Release kapısı</span>
            <strong>{rightsEvidenceReady ? "Hazır" : "Bekliyor"}</strong>
          </div>
          <dl>
            <div><dt>Hak durumu</dt><dd>{rightsStatusLabel(source.rights_status)}</dd></div>
            <div><dt>Lisans</dt><dd>{source.license}</dd></div>
            <div><dt>Kanıt</dt><dd>{source.license_evidence_ref ?? "Kanıt bekliyor"}</dd></div>
            {source.source_url && <div><dt>Kaynak URL</dt><dd>{source.source_url}</dd></div>}
          </dl>
          <p>{rightsEvidenceReady ? "Hak kapısı release için hazır." : "Release için hak durumu temizlenmeli ve lisans kanıtı kaydedilmelidir."}</p>
        </div>
      </section>

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

      <section className="inspector-section">
        <div className="section-heading">
          <h3><FileText size={16} /> Belge örnekleri</h3>
          <div className="header-actions">
            {canResample && (
              <button className="icon-button compact" type="button" disabled={resampling} title="Risk bazlı yeniden örnekle" onClick={() => void queueDocumentResample()}>
                <RefreshCw className={resampling ? "spin" : ""} size={15} />
              </button>
            )}
            <button className="icon-button compact" type="button" title="Sıradaki bekleyen örneği aç" onClick={() => void openNextPendingDocument()}>
              <ClipboardCheck size={15} />
            </button>
          </div>
        </div>
        <div className="document-progress">
          <div>
            <strong>{reviewedCount.toLocaleString("tr-TR")} / {sampleCount.toLocaleString("tr-TR")}</strong>
            <span>İncelenen örnek</span>
          </div>
          <div>
            <strong>{source.approved_document_count.toLocaleString("tr-TR")}</strong>
            <span>Onaylı</span>
          </div>
          <div>
            <strong>{source.flagged_document_count.toLocaleString("tr-TR")}</strong>
            <span>İşaretli</span>
          </div>
          <progress max={sampleCount || 1} value={reviewedCount} aria-label={`Örnek inceleme ilerlemesi yüzde ${reviewPercent}`} />
        </div>
        {qualitySummary && qualitySummary.review_count > 0 && (
          <div className="quality-summary">
            <div className="quality-summary-heading">
              <span>Çok boyutlu kalite</span>
              <strong>{qualitySummary.document_count.toLocaleString("tr-TR")} belge</strong>
            </div>
            <div className="quality-summary-grid">
              <QualityAverage label="Genel" value={qualitySummary.average_quality_score} />
              <QualityAverage label="Dil" value={qualitySummary.average_language_quality_score} />
              <QualityAverage label="Tutarlılık" value={qualitySummary.average_coherence_score} />
              <QualityAverage label="Bilgi" value={qualitySummary.average_information_density_score} />
              <QualityAverage label="Temizlik" value={qualitySummary.average_cleanliness_score} />
            </div>
            {qualitySummary.legacy_review_count > 0 && <small>{qualitySummary.legacy_review_count.toLocaleString("tr-TR")} eski tek puanlı kayıt özete katılmadı.</small>}
          </div>
        )}
        {sampleGenerations.length > 0 && (
          <div className="sample-generation-list" aria-label="Örnek nesilleri">
            {sampleGenerations.map((generation) => (
              <div key={generation.generation}>
                <span>Nesil {generation.generation}</span>
                <strong className={generation.status}>{generation.status === "active" ? "Aktif" : "Arşiv"}</strong>
                <small>{generation.sample_count.toLocaleString("tr-TR")} örnek · {generation.sampling_method} · {formatDate(generation.created_at)}</small>
              </div>
            ))}
          </div>
        )}
        <div className="document-filter-tabs" role="tablist" aria-label="Belge örneği filtresi">
          <button type="button" aria-pressed={documentStatusFilter === "pending"} onClick={() => setDocumentStatusFilter("pending")}>Bekleyen {pendingDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "risk"} onClick={() => setDocumentStatusFilter("risk")}>Riskli {riskyDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "approved"} onClick={() => setDocumentStatusFilter("approved")}>Onaylı {approvedDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "flagged"} onClick={() => setDocumentStatusFilter("flagged")}>İşaretli {flaggedDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "all"} onClick={() => setDocumentStatusFilter("all")}>Tümü {documents.length}</button>
        </div>
        {canReview && selectableDocuments.length > 0 && !["approved", "flagged"].includes(documentStatusFilter) && (
          <form className="bulk-review-form" onSubmit={submitBulkDocumentReview}>
            <div className="bulk-selection-row">
              <label>
                <input
                  type="checkbox"
                  checked={selectableDocuments.length > 0 && selectableDocuments.every((document) => selectedDocumentIDs.has(document.id))}
                  onChange={(event) => toggleAllPendingDocuments(event.target.checked)}
                />
                {documentStatusFilter === "risk" ? "Riskli örnekleri seç" : "Tüm bekleyenleri seç"}
              </label>
              <strong>{selectedDocumentIDs.size.toLocaleString("tr-TR")} seçili</strong>
            </div>
            <div className="bulk-review-fields">
              <QualityRubricFields />
              <label className="bulk-review-reason">Ortak gerekçe<input name="reason" placeholder="Ret ve hassas kararda zorunlu" /></label>
            </div>
            <div className="review-actions">
              <button className="approve-button" type="submit" name="decision" value="approved" disabled={bulkReviewing || selectedDocumentIDs.size === 0}><Check size={16} />Onayla</button>
              <button className="warning-button" type="submit" name="decision" value="sensitive_review" disabled={bulkReviewing || selectedDocumentIDs.size === 0}><ShieldAlert size={16} />Hassas</button>
              <button className="danger-button" type="submit" name="decision" value="rejected" disabled={bulkReviewing || selectedDocumentIDs.size === 0}>{bulkReviewing ? <LoaderCircle className="spin" size={16} /> : <XCircle size={16} />}Reddet</button>
            </div>
          </form>
        )}
        <div className="document-list">
          {filteredDocuments.map((document) => {
            const canSelect = canReview && (document.status === "sampled" || document.status === "edited");
            return (
              <div key={document.id} className={`document-list-row${canSelect ? " selectable" : ""}`}>
                {canSelect && (
                  <input
                    type="checkbox"
                    aria-label={`Satır ${document.source_ordinal} seç`}
                    checked={selectedDocumentIDs.has(document.id)}
                    onChange={(event) => toggleDocumentSelection(document.id, event.target.checked)}
                  />
                )}
                <button className={`document-card ${document.status}`} type="button" onClick={() => void openDocument(document)}>
                  <span>#{document.source_ordinal}</span>
                  <strong>{document.text_preview}</strong>
                  <small><b>{documentStatusLabel(document.status)}</b> · v{document.current_version} · {document.char_count.toLocaleString("tr-TR")} karakter{document.risk_score > 0 && <span className="document-risk-score">Risk {document.risk_score}</span>}</small>
                  {document.risk_reasons.length > 0 && <small className="document-risk-reasons">{document.risk_reasons.map((reason) => riskReasonLabels[reason] ?? reason).join(" · ")}</small>}
                </button>
              </div>
            );
          })}
          {!loading && filteredDocuments.length === 0 && (
            <p className="muted-copy">
              {source.document_sampling_status === "failed" ? "Belge örnekleme işi başarısız." : documents.length === 0 ? "Henüz belge örneği oluşturulmadı." : "Bu filtrede örnek yok."}
            </p>
          )}
        </div>
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

      <dialog ref={documentDialog} className="source-dialog document-dialog">
        {activeDocument && (
          <div className="document-dialog-body">
            <div className="dialog-header">
              <div><span>Satır {activeDocument.source_ordinal} · sürüm {activeDocument.current_version}</span><h2>Belge örneği</h2></div>
              <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => documentDialog.current?.close()}><X size={19} /></button>
            </div>
            <label className="document-content-label">
              İçerik
              <textarea
                value={documentContent}
                onChange={(event) => setDocumentContent(event.target.value)}
                rows={16}
                readOnly={!canEditDocument}
              />
            </label>
            {canEditDocument && (
              <form className="document-edit-form" onSubmit={updateDocument}>
                <label>Düzenleme gerekçesi<input name="reason" placeholder="Kısa değişiklik notu" /></label>
                <div className="dialog-actions"><button className="primary-button" type="submit"><Save size={16} />Yeni sürümü kaydet</button></div>
              </form>
            )}
            {canReview && (
              <form className="document-review-form" onSubmit={submitDocumentReview}>
                <h3><CheckCircle2 size={16} /> Belge moderasyonu</h3>
                <div className="document-review-fields">
                  <QualityRubricFields />
                  <label>Karar gerekçesi<textarea name="reason" rows={2} placeholder="Ret ve hassas incelemede zorunlu" /></label>
                </div>
                <div className="review-actions">
                  <button className="approve-button" type="submit" name="decision" value="approved"><Check size={16} />Onayla</button>
                  <button className="warning-button" type="submit" name="decision" value="sensitive_review"><ShieldAlert size={16} />Hassas</button>
                  <button className="danger-button" type="submit" name="decision" value="rejected"><XCircle size={16} />Reddet</button>
                </div>
              </form>
            )}
            <div className="document-review-history">
              {documentReviews.map((review) => (
                <div key={review.id}>
                  <span className={`review-decision ${review.decision}`}>{review.decision}</span>
                  <div className="review-quality-values">
                    <strong>Genel {review.quality_score}/5</strong>
                    {review.rubric_version === "multidimensional-v1" ? (
                      <span>Dil {review.language_quality_score}/5 · Tutarlılık {review.coherence_score}/5 · Bilgi {review.information_density_score}/5 · Temizlik {review.cleanliness_score}/5</span>
                    ) : <span>Eski tek puanlı rubric</span>}
                  </div>
                  <small>v{review.document_version} · {formatDate(review.created_at)}</small>
                </div>
              ))}
            </div>
            <div className="dialog-actions"><button className="text-button" type="button" onClick={() => documentDialog.current?.close()}>Kapat</button></div>
          </div>
        )}
      </dialog>
    </aside>
  );
}

function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div><dt>{label}</dt><dd className={mono ? "mono" : undefined}>{value}</dd></div>;
}

function CorpusMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "watch" | "risk" }) {
  return <div className={`corpus-metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function QualityRubricFields() {
  return (
    <fieldset className="quality-rubric-fields">
      <legend>Kalite puanları</legend>
      <div>
        {qualityScoreFields.map((field) => (
          <label key={field.name} title={field.title}>
            {field.label}
            <input
              name={field.name}
              type="number"
              min="1"
              max="5"
              step="1"
              defaultValue="3"
              aria-label={`${field.label} kalite puanı`}
              required
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function QualityAverage({ label, value }: { label: string; value?: number }) {
  return <div><span>{label}</span><strong>{value === undefined ? "-" : value.toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}</strong></div>;
}

function readQualityScores(data: FormData): QualityScores | null {
  const scores = {} as QualityScores;
  for (const field of qualityScoreFields) {
    const value = Number(data.get(field.name));
    if (!Number.isInteger(value) || value < 1 || value > 5) return null;
    scores[field.name] = value;
  }
  return scores;
}

function findingSummary(scan: PIIScan) {
  const findings = Object.entries(scan.findings).filter(([, count]) => count > 0);
  if (findings.length === 0) return "Bulgu yok";
  return findings.map(([type, count]) => `${findingLabels[type] ?? type}: ${count}`).join(" · ");
}

function documentStatusLabel(status: Document["status"]) {
  const labels: Record<Document["status"], string> = {
    sampled: "Bekliyor",
    edited: "Düzenlendi",
    approved: "Onaylandı",
    rejected: "Reddedildi",
    sensitive_review: "Hassas",
  };
  return labels[status];
}

function rightsStatusLabel(status: string) {
  const labels: Record<string, string> = {
    unknown: "Bilinmiyor",
    cleared: "Temizlendi",
    restricted: "Kısıtlı",
    blocked: "Engelli",
  };
  return labels[status] ?? status;
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
