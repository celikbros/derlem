"use client";

import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Edit3,
  FileText,
  Fingerprint,
  History,
  LoaderCircle,
  RefreshCw,
  Scale,
  ScanLine,
  Save,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { JobStatus } from "@/components/jobs-panel";
import { EvidenceHash } from "@/components/evidence-hash";
import { messageFrom, requestJSON } from "@/lib/client-api";
import { readableParagraphs } from "@/lib/readable-document";
import type { BackgroundJob, Document, DocumentQualitySummary, DocumentReview, DocumentReviewClaim, DocumentReviewHistoryItem, DocumentSampleGeneration, PIIScan, Review, ReverseDocumentReviewResult, Source, User } from "@/lib/types";

const purposeLabels: Record<string, string> = {
  pretrain: "Pretrain",
  instruction: "Instruction",
  preference: "Preference",
  eval: "Eval",
  holdout: "Holdout",
  post_training: "Post-training",
};

const distillationProviders: Record<string, { label: string; model: string }> = {
  anthropic: { label: "Claude (Anthropic)", model: "claude-opus-4-8" },
  openai: { label: "ChatGPT (OpenAI)", model: "gpt-4o" },
  google: { label: "Gemini (Google)", model: "gemini-1.5-pro" },
  xai: { label: "Grok (xAI)", model: "grok-2-latest" },
  alibaba: { label: "Qwen (Alibaba)", model: "qwen-plus" },
  echo: { label: "Echo (test, ağ gerektirmez)", model: "echo" },
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
type ReviewHistoryDecision = DocumentReview["decision"] | "reversed";
type ReviewHistoryFilter = "all" | ReviewHistoryDecision;

type ReviewPreset = {
  id: string;
  label: string;
  description: string;
  reason: string;
  scores: QualityScores;
};

const reviewPresets: ReviewPreset[] = [
  {
    id: "spam",
    label: "Reklam / ilan / SEO",
    description: "Reklam, ilan veya arama motoru anahtar kelime yığını.",
    reason: "Reklam, ilan veya SEO amaçlı anahtar kelime yığını içeriyor. Doğal ve temiz eğitim verisi olarak kullanılamaz.",
    scores: { quality_score: 1, language_quality_score: 2, coherence_score: 1, information_density_score: 1, cleanliness_score: 1 },
  },
  {
    id: "repetition",
    label: "Aşırı tekrar / hashtag",
    description: "Hashtag, sözcük veya bölüm tekrarları içeriği bastırıyor.",
    reason: "Aşırı hashtag, sözcük veya bölüm tekrarı içeriyor; anlamlı içerik gürültü içinde kalıyor. Temiz eğitim verisi olarak kullanılamaz.",
    scores: { quality_score: 1, language_quality_score: 2, coherence_score: 1, information_density_score: 1, cleanliness_score: 1 },
  },
  {
    id: "merged",
    label: "İlgisiz içerikler birleşmiş",
    description: "Bağımsız metinler tek belgeye karışmış; konu akışı yok.",
    reason: "Birden fazla bağımsız içerik tek belgede birleşmiş; konu ve belge sınırları bozuk. Temiz eğitim verisi olarak doğrudan kullanılamaz.",
    scores: { quality_score: 2, language_quality_score: 3, coherence_score: 1, information_density_score: 2, cleanliness_score: 1 },
  },
  {
    id: "ocr",
    label: "OCR / kodlama bozuk",
    description: "Bozuk karakterler ve yazım hataları okunabilirliği bozuyor.",
    reason: "OCR veya kodlama hataları ile bozuk/görünmez karakterler okunabilirliği bozuyor. Temiz eğitim verisi olarak doğrudan kullanılamaz.",
    scores: { quality_score: 2, language_quality_score: 1, coherence_score: 2, information_density_score: 2, cleanliness_score: 1 },
  },
  {
    id: "navigation",
    label: "Menü / navigasyon artığı",
    description: "Sayfa menüsü, bağlantılar veya kaynakça artıkları baskın.",
    reason: "Sayfa menüsü, navigasyon, bağlantı veya benzeri web artıkları içeriğe karışmış ve metin bütünlüğünü bozuyor.",
    scores: { quality_score: 2, language_quality_score: 3, coherence_score: 2, information_density_score: 2, cleanliness_score: 1 },
  },
  {
    id: "meaningless",
    label: "Anlamsız / yetersiz içerik",
    description: "Anlamlı eğitim içeriği yok veya içerik yetersiz.",
    reason: "Anlamlı ve yeterli eğitim içeriği bulunmuyor; belge bağlamsız, parçalı veya kullanılamayacak kadar yetersiz.",
    scores: { quality_score: 1, language_quality_score: 2, coherence_score: 1, information_density_score: 1, cleanliness_score: 2 },
  },
];

export function SourceInspector({
  source,
  user,
  reviewMode = false,
  onClose,
  onChanged,
  onRefresh,
  onNotice,
}: {
  source: Source;
  user: User;
  reviewMode?: boolean;
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
  const [documentReviewHistory, setDocumentReviewHistory] = useState<DocumentReviewHistoryItem[]>([]);
  const [reviewHistoryFilter, setReviewHistoryFilter] = useState<ReviewHistoryFilter>("all");
  const [activeDocument, setActiveDocument] = useState<Document | null>(null);
  const [documentReviews, setDocumentReviews] = useState<DocumentReview[]>([]);
  const [qualitySummary, setQualitySummary] = useState<DocumentQualitySummary | null>(null);
  const [sampleGenerations, setSampleGenerations] = useState<DocumentSampleGeneration[]>([]);
  const [documentContent, setDocumentContent] = useState("");
  const [selectedDocumentIDs, setSelectedDocumentIDs] = useState<Set<string>>(new Set());
  const [bulkReviewing, setBulkReviewing] = useState(false);
  const [reviewClaim, setReviewClaim] = useState<DocumentReviewClaim | null>(null);
  const [claimBatchSize, setClaimBatchSize] = useState(20);
  const [claiming, setClaiming] = useState(false);
  const [documentReviewing, setDocumentReviewing] = useState(false);
  const [reversingReviewID, setReversingReviewID] = useState<string | null>(null);
  const [selectedReviewPresetID, setSelectedReviewPresetID] = useState<string | null>(null);
  const [resampling, setResampling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [distilling, setDistilling] = useState(false);
  const [distillProvider, setDistillProvider] = useState("echo");
  const editDialog = useRef<HTMLDialogElement>(null);
  const documentDialog = useRef<HTMLDialogElement>(null);
  const reviewClaimRef = useRef<DocumentReviewClaim | null>(null);
  const claimedSourceRef = useRef(source.id);

  useEffect(() => {
    reviewClaimRef.current = reviewClaim;
  }, [reviewClaim]);

  useEffect(() => {
    if (claimedSourceRef.current === source.id) return;
    const token = reviewClaimRef.current?.claim_token;
    if (token) {
      void fetch(`/api/document-review-claims/${encodeURIComponent(token)}`, { method: "DELETE" });
    }
    claimedSourceRef.current = source.id;
    reviewClaimRef.current = null;
    setReviewClaim(null);
    setSelectedDocumentIDs(new Set());
  }, [source.id]);

  useEffect(() => {
    const token = reviewClaim?.claim_token;
    if (!token) return;
    const timer = window.setInterval(() => {
      void requestJSON<{ expires_at: string; document_count: number }>(
        `/api/document-review-claims/${encodeURIComponent(token)}/renew`,
        { method: "POST" },
      ).then((renewal) => {
        setReviewClaim((current) => current?.claim_token === token
          ? { ...current, expires_at: renewal.expires_at }
          : current);
      }).catch((error) => {
        setReviewClaim(null);
        setSelectedDocumentIDs(new Set());
        onNotice(messageFrom(error));
      });
    }, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [onNotice, reviewClaim?.claim_token]);

  const canReadJobs = user.roles.some((role) => ["admin", "data_manager"].includes(role));

  const loadDocumentReviewHistory = useCallback(async () => {
    if (!reviewMode) {
      setDocumentReviewHistory([]);
      return;
    }
    try {
      const payload = await requestJSON<{ items: DocumentReviewHistoryItem[] }>(
        `/api/sources/${source.id}/document-review-history`,
      );
      setDocumentReviewHistory(payload.items);
    } catch (error) {
      onNotice(messageFrom(error));
    }
  }, [onNotice, reviewMode, source.id]);

  const loadActivity = useCallback(async () => {
    try {
      const jobRequest = canReadJobs
        ? requestJSON<{ items: BackgroundJob[] }>(`/api/jobs?source_id=${source.id}&limit=20`)
        : Promise.resolve({ items: [] as BackgroundJob[] });
      const [reviewPayload, scanPayload, jobPayload, documentPayload, generationPayload, qualityPayload] = await Promise.all([
        requestJSON<{ items: Review[] }>(`/api/sources/${source.id}/reviews`),
        requestJSON<{ items: PIIScan[] }>(`/api/sources/${source.id}/pii-scans`),
        jobRequest,
        requestJSON<{ items: Document[] }>(`/api/sources/${source.id}/documents?limit=200`),
        requestJSON<{ items: DocumentSampleGeneration[] }>(`/api/sources/${source.id}/document-sample-generations`),
        requestJSON<DocumentQualitySummary>(`/api/sources/${source.id}/document-quality-summary`),
      ]);
      setReviews(reviewPayload.items);
      setScans(scanPayload.items);
      setJobs(jobPayload.items);
      const mergedDocuments = new Map(documentPayload.items.map((document) => [document.id, document]));
      reviewClaimRef.current?.documents.forEach((document) => mergedDocuments.set(document.id, document));
      const visibleDocuments = [...mergedDocuments.values()];
      setDocuments(visibleDocuments);
      setSampleGenerations(generationPayload.items);
      setQualitySummary(qualityPayload);
      const pendingIDs = new Set(visibleDocuments
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
  }, [canReadJobs, onNotice, onRefresh, source.document_sampling_status, source.duplicate_status, source.id, source.normalized_dedup_status, source.object_sha256, source.pii_status]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadActivity(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadActivity, source.version]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadDocumentReviewHistory(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDocumentReviewHistory, source.version]);

  // Kaynak değişince seçim/özet render sırasında sıfırlanır ve yükleme
  // göstergesi açılır (effect içinde senkron setState yerine React'in
  // "adjust state during render" deseni).
  const [prevSourceID, setPrevSourceID] = useState(source.id);
  if (prevSourceID !== source.id) {
    setPrevSourceID(source.id);
    setSelectedDocumentIDs(new Set());
    setDocumentReviewHistory([]);
    setReviewHistoryFilter("all");
    setQualitySummary(null);
    setLoading(true);
  }
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
  const claimedDocumentIDs = new Set(reviewClaim?.documents.map((document) => document.id) ?? []);
  const claimedPendingDocuments = pendingDocuments.filter((document) => claimedDocumentIDs.has(document.id));
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
  const displayedDocuments = reviewMode ? claimedPendingDocuments : filteredDocuments;
  const selectableDocuments = (documentStatusFilter === "risk" ? riskyDocuments : pendingDocuments)
    .filter((document) => claimedDocumentIDs.has(document.id));
  const riskSampleCount = documents.filter((document) => document.risk_score > 0).length;
  const reviewHistoryEntries = documentReviewHistory
    .map((item) => ({
      ...item,
      decision: currentReviewHistoryDecision(item),
      latestAt: latestReviewDate(item.reviews),
    }))
    .sort((left, right) =>
      right.latestAt.localeCompare(left.latestAt)
      || left.document.source_ordinal - right.document.source_ordinal
    );
  const reviewHistoryCounts: Record<ReviewHistoryFilter, number> = {
    all: reviewHistoryEntries.length,
    approved: reviewHistoryEntries.filter((item) => item.decision === "approved").length,
    rejected: reviewHistoryEntries.filter((item) => item.decision === "rejected").length,
    sensitive_review: reviewHistoryEntries.filter((item) => item.decision === "sensitive_review").length,
    reversed: reviewHistoryEntries.filter((item) => item.decision === "reversed").length,
  };
  const displayedReviewHistory = reviewHistoryFilter === "all"
    ? reviewHistoryEntries
    : reviewHistoryEntries.filter((item) => item.decision === reviewHistoryFilter);
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

  async function distillSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const topics = String(data.get("topics") ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
    const count = Number(data.get("count") ?? 0);
    if (topics.length === 0 && count < 1) {
      onNotice("Konu listesi girin veya belge sayısını 1'e çıkarın.");
      return;
    }
    setDistilling(true);
    try {
      const result = await requestJSON<{ job_id: string }>(`/api/sources/${source.id}/distill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: String(data.get("provider") ?? "echo"),
          model: String(data.get("model") ?? ""),
          system_prompt: String(data.get("system_prompt") ?? ""),
          prompt_template: String(data.get("prompt_template") ?? ""),
          topics,
          count,
          max_tokens: 2000,
          temperature: 1.0,
        }),
      });
      form.reset();
      onNotice(`Distilasyon kuyruğa alındı: ${result.job_id.slice(0, 8)}`);
      await loadActivity();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setDistilling(false);
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
      setSelectedReviewPresetID(null);
      if (!documentDialog.current?.open) documentDialog.current?.showModal();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }

  async function acquireReviewClaim() {
    setClaiming(true);
    try {
      const claim = await requestJSON<DocumentReviewClaim>(`/api/sources/${source.id}/documents/claims`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: claimBatchSize }),
      });
      if (claim.documents.length === 0) {
        onNotice("Dağıtılabilecek bekleyen belge kalmadı veya tüm belgeler başka inceleyicilerde.");
        return;
      }
      setReviewClaim(claim);
      setSelectedDocumentIDs(new Set());
      setDocuments((current) => {
        const merged = new Map(current.map((document) => [document.id, document]));
        claim.documents.forEach((document) => merged.set(document.id, document));
        return [...merged.values()];
      });
      setDocumentStatusFilter("pending");
      onNotice(claim.resumed
        ? `Mevcut ${claim.documents.length.toLocaleString("tr-TR")} belgeli iş paketiniz sürdürüldü.`
        : `${claim.documents.length.toLocaleString("tr-TR")} belgeli güvenli iş paketi alındı.`
      );
      if (reviewMode && claim.documents.length > 0) {
        await openDocument(claim.documents[0]);
      }
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setClaiming(false);
    }
  }

  async function releaseReviewClaim() {
    const token = reviewClaim?.claim_token;
    if (!token) return;
    setClaiming(true);
    try {
      const response = await fetch(`/api/document-review-claims/${encodeURIComponent(token)}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload?.error?.message ?? "İş paketi bırakılamadı.");
      }
      setReviewClaim(null);
      setSelectedDocumentIDs(new Set());
      onNotice("İş paketi güvenle bırakıldı; kalan belgeler yeniden dağıtılabilir.");
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setClaiming(false);
    }
  }

  async function openNextPendingDocument() {
    const nextDocument = claimedPendingDocuments[0];
    if (!nextDocument) {
      onNotice(reviewClaim ? "Bu iş paketinde bekleyen örnek kalmadı." : "Önce güvenli bir iş paketi alın.");
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
      setReviewClaim((current) => {
        if (!current) return current;
        const remaining = current.documents.filter((document) => document.id !== updated.id);
        return remaining.length > 0 ? { ...current, documents: remaining } : null;
      });
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
    if (!activeDocument || !reviewClaim || !claimedDocumentIDs.has(activeDocument.id)) {
      onNotice("Bu belge size atanmış geçerli bir iş paketinde değil.");
      return;
    }
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
    if (decision === 'approved' && selectedReviewPresetID) {
      onNotice('Bir ret nedeni seçiliyken belge onaylanamaz. Onaylamak için önce ret şablonunu temizleyin.');
      return;
    }
    const decisionLabels: Record<string, string> = {
      approved: "Onayla",
      sensitive_review: "Hassas olarak işaretle",
      rejected: "Reddet",
    };
    if (!window.confirm(`${decisionLabels[decision] ?? decision} kararı kaydedilsin mi? Bu karar denetim geçmişine yazılır.`)) {
      return;
    }
    setDocumentReviewing(true);
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
            claim_token: reviewClaim.claim_token,
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
      const remainingClaimDocuments = reviewClaim.documents.filter((document) => document.id !== payload.document.id);
      setReviewClaim(remainingClaimDocuments.length > 0 ? { ...reviewClaim, documents: remainingClaimDocuments } : null);
      onChanged(payload.source);
      await loadDocumentReviewHistory();
      form.reset();
      setSelectedReviewPresetID(null);
      const nextClaimed = remainingClaimDocuments[0];
      const nextPending = nextClaimed
        ? updatedDocuments.find((document) =>
          document.id === nextClaimed.id
          && (document.status === "sampled" || document.status === "edited")
        )
        : undefined;
      if (nextPending) {
        onNotice("Belge inceleme kararı kaydedildi. Sıradaki örnek açılıyor.");
        await openDocument(nextPending);
      } else {
        documentDialog.current?.close();
        onNotice("Belge inceleme kararı kaydedildi. Bekleyen örnek kalmadı.");
      }
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setDocumentReviewing(false);
    }
  }

  async function reverseDocumentReview(review: DocumentReview) {
    const enteredReason = window.prompt(
      "Geri alma gerekçesi:",
      "Yanlış karar verildi; belge yeniden incelenecek.",
    );
    const reason = enteredReason?.trim();
    if (!reason) return;
    if (!window.confirm(
      `${reviewDecisionLabel(review.decision)} kararı geri alınsın mı? Eski kayıt silinmez; geri alma denetim geçmişine eklenir.`,
    )) return;

    setReversingReviewID(review.id);
    try {
      const payload = await requestJSON<ReverseDocumentReviewResult>(
        `/api/document-reviews/${review.id}/reversal`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason }),
        },
      );
      setActiveDocument(payload.document);
      setDocuments((current) => current.map((document) =>
        document.id === payload.document.id ? payload.document : document
      ));
      setDocumentReviews((current) => current.map((item) =>
        item.id === payload.review.id ? payload.review : item
      ));
      setSelectedDocumentIDs((current) => {
        const next = new Set(current);
        next.delete(payload.document.id);
        return next;
      });
      onChanged(payload.source);
      onNotice(payload.already_reversed
        ? "Bu karar daha önce geri alınmıştı."
        : "Karar geri alındı; belge yeniden Bekleyen durumuna döndü."
      );
      await loadActivity();
      await loadDocumentReviewHistory();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setReversingReviewID(null);
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
    if (!decision || selectedDocumentIDs.size === 0 || !reviewClaim) return;
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
    if (!confirmReviewDecision(decision, selectedDocuments.length)) return;

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
          claim_token: reviewClaim.claim_token,
          ...qualityScores,
        }),
      });
      const updatedByID = new Map(payload.documents.map((document) => [document.id, document]));
      setDocuments((current) => current.map((document) => updatedByID.get(document.id) ?? document));
      setSelectedDocumentIDs(new Set());
      const reviewedIDs = new Set(payload.documents.map((document) => document.id));
      const remainingClaimDocuments = reviewClaim.documents.filter((document) => !reviewedIDs.has(document.id));
      setReviewClaim(remainingClaimDocuments.length > 0 ? { ...reviewClaim, documents: remainingClaimDocuments } : null);
      onChanged(payload.source);
      form.reset();
      onNotice(`${payload.documents.length.toLocaleString("tr-TR")} belge için toplu karar kaydedildi.`);
    } catch (error) {
      setReviewClaim(null);
      setSelectedDocumentIDs(new Set());
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
    if (!window.confirm(`Kaynak için ${reviewDecisionLabel(decision)} kararı kaydedilsin mi? Bu işlem denetim geçmişine yazılır.`)) return;
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

  const profileEvidenceFields = (
    <div className="profile-evidence-grid">
      {!reviewMode && (
        <div className="evidence-field">
          <span>Veri profili</span>
          <strong>{source.data_profile_key} · sürüm {source.data_profile_version}</strong>
        </div>
      )}
      <div className="evidence-field">
        <span>Profil ataması</span>
        <strong>{profileAssignmentLabel(source.profile_assignment_reason)}</strong>
      </div>
      <div className="evidence-field">
        <span>Veri kökeni</span>
        <strong>{dataOriginLabel(source.data_origin)}</strong>
      </div>
      <div className="evidence-field">
        <span>Üretim çalışması</span>
        <strong className={source.production_run_id ? "mono" : undefined}>{source.production_run_id ? shortenIdentifier(source.production_run_id) : "Bağlı çalışma yok"}</strong>
      </div>
      <div className="evidence-field wide">
        <span>Profil yapılandırması</span>
        <strong>{source.profile_config_artifact_kind}</strong>
        <EvidenceHash label="Profil yapılandırma SHA256" value={source.profile_config_sha256} />
      </div>
    </div>
  );
  const profileEvidenceTechnical = (
    <dl>
      <Detail label="Profil atama zamanı" value={formatDate(source.profile_assigned_at)} />
      <Detail label="Profil atama kodu" value={source.profile_assignment_reason} mono />
      <Detail label="Köken kodu" value={source.data_origin} mono />
      {source.production_run_id && <Detail label="Üretim çalışması kimliği" value={source.production_run_id} mono />}
      {reviewMode && reviewClaim?.review_campaign_id && <Detail label="İnceleme kampanyası kimliği" value={reviewClaim.review_campaign_id} mono />}
    </dl>
  );

  return (
    <aside className={`inspector${reviewMode ? " review-workspace-panel" : ""}`} aria-label={reviewMode ? "Belge inceleme çalışma alanı" : "Kaynak ayrıntısı"}>
      <div className="inspector-header">
        <div>
          <span>{reviewMode ? "Odaklı belge inceleme" : "Kaynak ayrıntısı"}</span>
          <h2>{source.name}</h2>
          {reviewMode && <p className="review-workspace-subtitle">{pendingDocuments.length.toLocaleString("tr-TR")} bekleyen örnek · {riskyDocuments.length.toLocaleString("tr-TR")} riskli · {reviewedCount.toLocaleString("tr-TR")} tamamlandı</p>}
        </div>
        <div className="header-actions">
          {canManageSource && <button className="icon-button" type="button" title="Metadata düzenle" onClick={() => editDialog.current?.showModal()}><Edit3 size={17} /></button>}
          <button className="icon-button review-back-button" type="button" title={reviewMode ? "İnceleme kuyruğuna dön" : "Ayrıntıyı kapat"} onClick={onClose}>
            {reviewMode ? <ArrowLeft size={18} /> : <X size={18} />}
          </button>
        </div>
      </div>

      {reviewMode && (
        <section className="review-workspace-guide" aria-label="İnceleme adımları">
          <strong>Burada yalnız üç şey yapacaksınız</strong>
          <ol>
            <li><b>Paketi al:</b> en riskli 10-20 bekleyen belge yalnız size ayrılsın.</li>
            <li><b>Belgeyi oku:</b> tam metin ayrı pencerede açılır.</li>
            <li><b>Karar ver:</b> beş puanı girip Onayla, Hassas veya Reddet seçin.</li>
          </ol>
        </section>
      )}

      <dl>
        <Detail label="Amaç" value={purposeLabels[source.content_purpose]} />
        <Detail label="Kaynak tipi" value={source.source_type} />
        <Detail label="Lisans" value={source.license} />
        <Detail label="Hak durumu" value={source.rights_status} />
        <Detail label="Dil / alan" value={`${source.language} / ${source.domain}`} />
        <Detail label="Köken" value={source.lineage_ref} mono />
        {source.derived_from_source_id && (
          <Detail label="Türetildiği kaynak" value={source.derived_from_source_id} mono />
        )}
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

      {reviewMode ? (
        <details className="review-profile-evidence" data-testid="source-profile-evidence">
          <summary>
            <span className="review-profile-evidence-title" role="heading" aria-level={3}><Fingerprint size={15} aria-hidden="true" /> Profil ve kanıt</span>
            <strong>{source.data_profile_key} · sürüm {source.data_profile_version}</strong>
            <span className="evidence-status-chip">Salt okunur</span>
          </summary>
          <div className="review-profile-evidence-body">
            <p className="profile-evidence-lead">Bu kaynağın hangi sürümlü kurallarla işlendiğini ve kanıt zincirini gösterir.</p>
            {profileEvidenceFields}
            <div className="review-profile-evidence-technical">
              <strong>Teknik ayrıntılar</strong>
              {profileEvidenceTechnical}
            </div>
          </div>
        </details>
      ) : (
        <section className="inspector-section profile-evidence-section" data-testid="source-profile-evidence">
          <div className="section-heading">
            <h3><Fingerprint size={16} /> Profil ve kanıt</h3>
            <span className="evidence-status-chip">Salt okunur</span>
          </div>
          <p className="profile-evidence-lead">Bu kaynağın hangi sürümlü kurallarla işlendiğini ve kanıt zincirini gösterir.</p>
          {profileEvidenceFields}
          <details className="evidence-technical">
            <summary>Teknik ayrıntılar</summary>
            {profileEvidenceTechnical}
          </details>
        </section>
      )}

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
            <label>Dosya<input name="file" type="file" accept=".txt,.jsonl,.json,.csv,.tsv,.pdf,.docx,text/plain,application/json,application/pdf" required /></label>
            <p className="muted-copy">Metin (TXT/JSONL/CSV) doğrudan alınır; PDF ve Word (DOCX) belgeleri otomatik olarak metne çevrilir.</p>
            <button className="secondary-button" type="submit" disabled={uploading}>
              {uploading ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
              {uploading ? "Yükleniyor" : "Dosyayı yükle"}
            </button>
          </form>
        </section>
      )}

      {canIngestSource && !source.object_sha256 && (
        <section className="inspector-section">
          <h3><Sparkles size={16} /> Distilasyon (LLM’den üretim)</h3>
          <form className="ingest-form" onSubmit={distillSource}>
            <label>
              Sağlayıcı
              <select name="provider" value={distillProvider} onChange={(event) => setDistillProvider(event.target.value)}>
                {Object.entries(distillationProviders).map(([key, p]) => <option key={key} value={key}>{p.label}</option>)}
              </select>
            </label>
            <label>Model<input name="model" defaultValue={distillationProviders[distillProvider]?.model ?? ""} key={distillProvider} /></label>
            <label>Sistem yönergesi (opsiyonel)<textarea name="system_prompt" rows={2} placeholder="Sen bir Türkçe ders kitabı yazarısın." /></label>
            <label>Prompt şablonu (&#123;konu&#125; yer tutucusu kullanılabilir)<textarea name="prompt_template" rows={2} required placeholder="{konu} konusunu lise seviyesinde açıkla." /></label>
            <label>Konular (her satır bir belge; boşsa aşağıdaki sayı kadar tekrarlar)<textarea name="topics" rows={3} placeholder={"newton yasaları\nfotosentez\nosmanlı tarihi"} /></label>
            <label>Konu yoksa belge sayısı<input name="count" type="number" min={0} max={500} defaultValue={0} /></label>
            <p className="muted-copy">API anahtarı arayüze GİRİLMEZ; seçilen sağlayıcının sabit anahtarı yalnız worker ortamından okunur ve hiçbir yere yazılmaz. Test için ağ gerektirmeyen “Echo” sağlayıcısını kullanabilirsiniz. Üretilen içerik yine PII, tekrar ve insan inceleme kapılarından geçer.</p>
            <button className="secondary-button" type="submit" disabled={distilling}>
              {distilling ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
              {distilling ? "Kuyruğa alınıyor" : "Üret"}
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
          <button className="icon-button compact" type="button" title="Ayrıntıları yenile" onClick={() => { setLoading(true); void loadActivity(); }}>
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

      <section className="inspector-section review-documents-section">
        <div className="section-heading">
          <h3><FileText size={16} /> {reviewMode ? "Yeni inceleme paketi" : "Belge örnekleri"}</h3>
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
        {canReview && (
          <div className="bulk-review-form" aria-label="Güvenli inceleme iş paketi">
            {reviewClaim ? (
              <div className="bulk-selection-row">
                <span>
                  <strong>{reviewClaim.documents.length.toLocaleString("tr-TR")}</strong> belge size ayrıldı · süre {formatDate(reviewClaim.expires_at)}
                </span>
                <div className="review-claim-actions">
                  {reviewMode && <button className="primary-button" type="button" onClick={() => void openNextPendingDocument()}><ClipboardCheck size={16} />Sıradaki belgeyi aç</button>}
                  <button className="text-button" type="button" disabled={claiming} onClick={() => void releaseReviewClaim()}>
                    Paketi bırak
                  </button>
                </div>
              </div>
            ) : (
              <div className="bulk-selection-row">
                <label>
                  Paketteki belge
                  <select value={claimBatchSize} onChange={(event) => setClaimBatchSize(Number(event.target.value))}>
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    {!reviewMode && <option value={50}>50</option>}
                    {!reviewMode && <option value={100}>100</option>}
                    {!reviewMode && <option value={200}>200</option>}
                  </select>
                </label>
                <button className="primary-button" type="button" disabled={claiming || source.document_sampling_status !== "sampled" || reviewedCount >= sampleCount} onClick={() => void acquireReviewClaim()}>
                  {claiming ? <LoaderCircle className="spin" size={16} /> : <ClipboardCheck size={16} />}
                  {reviewMode ? "Paketi al ve incelemeye başla" : "Güvenli paket al"}
                </button>
              </div>
            )}
            <small>Belgeler 15 dakika boyunca yalnız size atanır; açık oturum paketi otomatik yeniler.</small>
          </div>
        )}
        {reviewMode && (
          <p className="review-package-order" role="note">
            <strong>Nereden başlar?</strong> Sistem yalnız <b>Bekleyen</b> ve başka bir inceleyiciye
            ayrılmamış belgeleri seçer. Risk puanı yüksek olan önce gelir; eşit puanda satır
            numarası küçük olan öne alınır. Tamamlanan belgeler yeni pakete girmez. Geri alınan
            bir kararın belgesi Bekleyen kuyruğuna döner ve sonraki paketlerden birine yeniden
            atanabilir.
          </p>
        )}
        {!reviewMode && <div className="document-filter-tabs" role="tablist" aria-label="Belge örneği filtresi">
          <button type="button" aria-pressed={documentStatusFilter === "pending"} onClick={() => setDocumentStatusFilter("pending")}>Bekleyen {pendingDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "risk"} onClick={() => setDocumentStatusFilter("risk")}>Riskli {riskyDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "approved"} onClick={() => setDocumentStatusFilter("approved")}>Onaylı {approvedDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "flagged"} onClick={() => setDocumentStatusFilter("flagged")}>İşaretli {flaggedDocuments.length}</button>
          <button type="button" aria-pressed={documentStatusFilter === "all"} onClick={() => setDocumentStatusFilter("all")}>Tümü {documents.length}</button>
        </div>}
        {canReview && !reviewMode && selectableDocuments.length > 0 && !["approved", "flagged"].includes(documentStatusFilter) && (
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
          {displayedDocuments.map((document) => {
            const canSelect = !reviewMode && canReview && claimedDocumentIDs.has(document.id) && (document.status === "sampled" || document.status === "edited");
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
          {!loading && displayedDocuments.length === 0 && (
            <p className="muted-copy">
              {reviewMode && !reviewClaim
                ? "Başlamak için yukarıdaki “Paketi al ve incelemeye başla” düğmesine basın."
                : source.document_sampling_status === "failed" ? "Belge örnekleme işi başarısız." : documents.length === 0 ? "Henüz belge örneği oluşturulmadı." : "Bu filtrede örnek yok."}
            </p>
          )}
        </div>
      </section>

      {reviewMode && (
        <section
          className="inspector-section reviewed-documents-section"
          data-testid="document-review-history"
        >
          <div className="section-heading">
            <h3><History size={16} /> İncelediklerim</h3>
            <span className="review-history-total">{reviewHistoryCounts.all.toLocaleString("tr-TR")} belge</span>
          </div>
          <p className="reviewed-documents-intro">
            Burada yalnız sizin bu kaynak için verdiğiniz kararlar ve geri alma kayıtlarınız
            görünür. Yeni paketteki bekleyen belgelerden bağımsızdır.
          </p>
          <p className="review-history-help">
            Bir kararı değiştirmek için belgeyi açın; <b>Geçmiş</b> bölümündeki
            <b> Kararı geri al</b> düğmesini kullanın. Eski kayıt silinmez. Belge Bekleyen
            kuyruğuna döner ve yeniden incelemek için daha sonraki bir pakette size veya başka
            bir inceleyiciye atanır.
          </p>
          <div className="reviewed-document-filter-tabs" role="tablist" aria-label="İncelediklerim filtresi">
            <button type="button" aria-pressed={reviewHistoryFilter === "all"} onClick={() => setReviewHistoryFilter("all")}>Tümü {reviewHistoryCounts.all}</button>
            <button type="button" aria-pressed={reviewHistoryFilter === "approved"} onClick={() => setReviewHistoryFilter("approved")}>Onaylı {reviewHistoryCounts.approved}</button>
            <button type="button" aria-pressed={reviewHistoryFilter === "rejected"} onClick={() => setReviewHistoryFilter("rejected")}>Reddedildi {reviewHistoryCounts.rejected}</button>
            <button type="button" aria-pressed={reviewHistoryFilter === "sensitive_review"} onClick={() => setReviewHistoryFilter("sensitive_review")}>Hassas {reviewHistoryCounts.sensitive_review}</button>
            <button type="button" aria-pressed={reviewHistoryFilter === "reversed"} onClick={() => setReviewHistoryFilter("reversed")}>Geri alındı {reviewHistoryCounts.reversed}</button>
          </div>
          <div className="document-list reviewed-document-list">
            {displayedReviewHistory.map((item) => (
              <div key={item.document.id} className="document-list-row">
                <button
                  className={`document-card review-history-${item.decision}`}
                  type="button"
                  onClick={() => void openDocument(item.document)}
                >
                  <span>#{item.document.source_ordinal}</span>
                  <strong>{item.document.text_preview}</strong>
                  <small>
                    <b>{reviewHistoryDecisionLabel(item.decision)}</b>
                    {" · "}{formatDate(item.latestAt)}
                    {" · "}{item.reviews.length.toLocaleString("tr-TR")} karar kaydı
                  </small>
                  {item.decision === "reversed" && (
                    <small className="review-history-queue-note">
                      Bekleyen kuyruğuna döndü; yeni bir pakete atanabilir.
                    </small>
                  )}
                </button>
              </div>
            ))}
            {!loading && displayedReviewHistory.length === 0 && (
              <p className="muted-copy">Bu filtrede size ait karar kaydı yok.</p>
            )}
          </div>
        </section>
      )}

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

      <dialog ref={documentDialog} className="source-dialog document-dialog" aria-labelledby="document-dialog-title">
        {activeDocument && (
          <div className="document-dialog-body">
            <div className="dialog-header">
              <div><span>Satır {activeDocument.source_ordinal} · sürüm {activeDocument.current_version}</span><h2 id="document-dialog-title">Belge örneği</h2></div>
              <button className="icon-button" type="button" title="Pencereyi kapat" aria-label="Pencereyi kapat" onClick={() => documentDialog.current?.close()}><X size={19} /></button>
            </div>
            <div className="document-review-layout">
              <section className="document-reading-pane" aria-labelledby="document-reading-title">
                <div className="document-reading-heading">
                  <div>
                    <h3 id="document-reading-title">Okuma görünümü</h3>
                    <p>Yalnız ekranda paragraflara ayrıldı; kaydedilen ham metin değişmedi.</p>
                  </div>
                  <span>{activeDocument.char_count.toLocaleString("tr-TR")} karakter</span>
                </div>

                {activeDocument.risk_reasons.length > 0 && (
                  <div className="document-risk-banner" role="note">
                    <strong>Otomatik uyarılar</strong>
                    <span>{activeDocument.risk_reasons.map((reason) => riskReasonLabels[reason] ?? reason).join(" · ")}</span>
                    <small>Uyarılar yardımcı sinyaldir; tek başına karar değildir.</small>
                  </div>
                )}

                <div className="readable-document" role="document" aria-label="Okuma görünümü" tabIndex={0}>
                  {readableParagraphs(documentContent).map((paragraph, paragraphIndex) => (
                    <p key={`${activeDocument.id}-paragraph-${paragraphIndex}`}>{paragraph}</p>
                  ))}
                </div>

                <details className="raw-document-details" open={canEditDocument}>
                  <summary>Ham metni göster</summary>
                  <label className="document-content-label">
                    Ham içerik
                    <textarea
                      value={documentContent}
                      onChange={(event) => setDocumentContent(event.target.value)}
                      rows={12}
                      readOnly={!canEditDocument}
                    />
                  </label>
                </details>

                {canEditDocument && (
                  <form className="document-edit-form" onSubmit={updateDocument}>
                    <label>Düzenleme gerekçesi<input name="reason" placeholder="Kısa değişiklik notu" /></label>
                    <div className="dialog-actions"><button className="primary-button" type="submit"><Save size={16} />Yeni sürümü kaydet</button></div>
                  </form>
                )}
              </section>

              <section className="document-decision-pane" aria-label="Belge kararı">
                <div className="review-decision-guide">
                  <strong>Tek karar sorusu</strong>
                  <p>Bu metin, düzeltme yapmadan eğitim verisine girebilir mi?</p>
                  <ul>
                    <li><b>Evet:</b> puanları kontrol edip Onayla.</li>
                    <li><b>Hayır:</b> uygun şablonu seçip Reddet.</li>
                    <li><b>Kişisel/mahrem veri şüphesi:</b> Hassas seçerek karantinaya al.</li>
                  </ul>
                  <small>Ret için baş, orta ve sondan en az iki bölgeyi doğrulayın. Onay için metni daha geniş okuyun.</small>
                </div>

                {canReview && claimedDocumentIDs.has(activeDocument.id) && (
                  <form
                    key={`${activeDocument.id}-${activeDocument.current_version}`}
                    className="document-review-form"
                    onSubmit={submitDocumentReview}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !(event.target instanceof HTMLTextAreaElement)) event.preventDefault();
                    }}
                  >
                    <h3><CheckCircle2 size={16} /> Belge moderasyonu</h3>
                    <div className="review-preset-section">
                      <span>Bu belge neden uygun değil?</span>
                      <small>Bir neden seçin; puanlar ve gerekçe doldurulur. Gerekirse düzenleyin, kararı siz gönderin.</small>
                      <div className="review-preset-grid">
                        {reviewPresets.map((preset) => (
                          <button
                            key={preset.id}
                            type="button"
                            aria-pressed={selectedReviewPresetID === preset.id}
                            onClick={(event) => {
                              applyReviewPreset(event.currentTarget.form, preset);
                              setSelectedReviewPresetID(preset.id);
                            }}
                          >
                            <strong>{preset.label}</strong>
                            <span>{preset.description}</span>
                          </button>
                        ))}
                      </div>
                      {selectedReviewPresetID && (
                        <div className="review-preset-selected" role="status">
                          <span>Ret şablonu seçili; Onayla kapatıldı.</span>
                          <button type="button" onClick={(event) => {
                            event.currentTarget.form?.reset();
                            setSelectedReviewPresetID(null);
                          }}>Şablonu temizle</button>
                        </div>
                      )}
                    </div>
                    <div className="document-review-fields">
                      <QualityRubricFields />
                      <label>
                        Karar gerekçesi
                        <textarea name="reason" rows={4} placeholder="Ret ve hassas incelemede zorunlu" />
                        <small className="reason-privacy-hint">Telefon, e-posta, IBAN veya başka kişisel değeri buraya kopyalamayın; yalnız sorun türünü yazın.</small>
                      </label>
                    </div>
                    <div className="review-actions">
                      <button className="approve-button" type="submit" name="decision" value="approved" disabled={documentReviewing || selectedReviewPresetID !== null}><Check size={16} />Onayla</button>
                      <button className="warning-button" type="submit" name="decision" value="sensitive_review" disabled={documentReviewing}><ShieldAlert size={16} />Hassas işaretle</button>
                      <button className="danger-button" type="submit" name="decision" value="rejected" disabled={documentReviewing}><XCircle size={16} />Reddet</button>
                    </div>
                  </form>
                )}

                <div className="document-review-history">
                  {documentReviews.map((review) => (
                    <div key={review.id} className={review.reversal ? "is-reversed" : undefined}>
                      <div className="review-history-heading">
                        <span className={`review-decision ${review.decision}`}>{review.decision}</span>
                        {review.reversal && <span className="review-reversal-badge">Geri alındı</span>}
                      </div>
                      <div className="review-quality-values">
                        <strong>Genel {review.quality_score}/5</strong>
                        {review.rubric_version === "multidimensional-v1" ? (
                          <span>Dil {review.language_quality_score}/5 · Tutarlılık {review.coherence_score}/5 · Bilgi {review.information_density_score}/5 · Temizlik {review.cleanliness_score}/5</span>
                        ) : <span>Eski tek puanlı rubric</span>}
                        {review.reason && <span className="review-history-reason">{review.reason}</span>}
                        {review.reversal && (
                          <span className="review-reversal-reason">
                            Geri alma gerekçesi: {review.reversal.reason}
                          </span>
                        )}
                      </div>
                      <small>v{review.document_version} · {formatDate(review.created_at)}</small>
                      {!review.reversal
                        && review.document_version === activeDocument.current_version
                        && activeDocument.status === decisionDocumentStatus(review.decision)
                        && (review.reviewer_id === user.id || user.roles.includes("admin"))
                        && (
                          <button
                            className="review-reversal-button"
                            type="button"
                            disabled={reversingReviewID === review.id}
                            onClick={() => reverseDocumentReview(review)}
                          >
                            {reversingReviewID === review.id ? "Geri alınıyor…" : "Kararı geri al"}
                          </button>
                        )}
                    </div>
                  ))}
                </div>
              </section>
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

function profileAssignmentLabel(value: Source["profile_assignment_reason"]) {
  return value === "declared_at_ingest" ? "Alım sırasında atandı" : value === "backfilled" ? "Geçmiş kayda uygulandı" : value;
}

function dataOriginLabel(value: Source["data_origin"]) {
  return value === "human" ? "İnsan üretimi" : value === "model" ? "Model üretimi" : value === "hybrid" ? "Karma üretim" : "Bilinmiyor";
}

function shortenIdentifier(value: string) {
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function CorpusMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "watch" | "risk" }) {
  return <div className={`corpus-metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function QualityRubricFields() {
  return (
    <fieldset className="quality-rubric-fields">
      <legend>Kalite puanları</legend>
      <p className="quality-rubric-scale">1 çok kötü · 2 sorunlu · 3 sınırda · 4 iyi · 5 çok iyi</p>
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
              defaultValue=""
              placeholder="–"
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

function reviewDecisionLabel(decision: string) {
  const labels: Record<string, string> = {
    approved: "Onayla",
    sensitive_review: "Hassas olarak işaretle",
    rejected: "Reddet",
  };
  return labels[decision] ?? decision;
}

function decisionDocumentStatus(decision: DocumentReview["decision"]): Document["status"] {
  return {
    approved: "approved",
    sensitive_review: "sensitive_review",
    rejected: "rejected",
  }[decision] as Document["status"];
}

function currentReviewHistoryDecision(item: DocumentReviewHistoryItem): ReviewHistoryDecision {
  const currentReview = [...item.reviews]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .find((review) => !review.reversal);
  return currentReview?.decision ?? "reversed";
}

function latestReviewDate(reviews: DocumentReview[]) {
  return reviews.reduce((latest, review) => {
    const eventDate = review.reversal?.created_at ?? review.created_at;
    return eventDate > latest ? eventDate : latest;
  }, new Date(0).toISOString());
}

function reviewHistoryDecisionLabel(decision: ReviewHistoryDecision) {
  return decision === "reversed" ? "Geri alındı" : documentStatusLabel(decision);
}

function confirmReviewDecision(decision: string, documentCount: number) {
  const subject = documentCount === 1 ? "Bu belge" : `${documentCount.toLocaleString("tr-TR")} belge`;
  return window.confirm(`${subject} için ${reviewDecisionLabel(decision)} kararı kaydedilsin mi? Karar denetim geçmişine yazılır.`);
}

function applyReviewPreset(form: HTMLFormElement | null, preset: ReviewPreset) {
  if (!form) return;
  for (const field of qualityScoreFields) {
    const input = form.elements.namedItem(field.name);
    if (input instanceof HTMLInputElement) {
      input.value = String(preset.scores[field.name]);
    }
  }
  const reason = form.elements.namedItem("reason");
  if (reason instanceof HTMLTextAreaElement) {
    reason.value = preset.reason;
    reason.focus();
  }
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
