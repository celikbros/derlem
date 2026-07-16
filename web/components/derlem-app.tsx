"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FilePlus2,
  FileText,
  GitCompareArrows,
  HelpCircle,
  Info,
  Library,
  ListTodo,
  LoaderCircle,
  LogIn,
  LogOut,
  PackageCheck,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ContributionsPanel } from "@/components/contributions-panel";
import { GuidePanel } from "@/components/guide-panel";
import { JobsPanel } from "@/components/jobs-panel";
import { ReleasePanel } from "@/components/release-panel";
import { SimilarityReviewPanel } from "@/components/similarity-review-panel";
import { SourceInspector } from "@/components/source-inspector";
import { UsersPanel } from "@/components/users-panel";
import { messageFrom, requestJSON } from "@/lib/client-api";
import { ROLE_INFO, roleInfoByRole, roleSummaryByLabel as accountHints } from "@/lib/roles";
import type { Source, User } from "@/lib/types";
import { APP_BUILD, APP_VERSION, versionLabel } from "@/lib/version";

type SourceList = {
  items: Source[];
  next_cursor?: string;
};

type ActiveView = "sources" | "review" | "similarity" | "releases" | "jobs" | "users" | "contribute" | "guide";

const sourceWorkspaceRoles = ["admin", "data_manager", "editor", "moderator", "expert_reviewer"];
const reviewerRoles = ["admin", "moderator", "expert_reviewer"];
const releaseRoles = ["admin", "data_manager", "consumer_team"];
const jobRoles = ["admin", "data_manager"];
const contributionViewRoles = ["admin", "data_manager", "contributor"];

const purposeLabels: Record<string, string> = {
  pretrain: "Pretrain",
  instruction: "Instruction",
  preference: "Preference",
  eval: "Eval",
  holdout: "Holdout",
  post_training: "Post-training",
};

const statusLabels: Record<string, string> = {
  source_registered: "Kaydedildi",
  license_review: "Hak incelemesi",
  raw_ingested: "Dosya alındı",
  normalized: "Normalize edildi",
  auto_checked: "Otomatik kontrol",
  sampled_for_review: "Örneklem incelemesi",
  approved_source: "Onaylandı",
  release_candidate: "Release adayı",
  rejected: "Reddedildi",
  quarantined: "Karantina",
};

const reviewStatuses = ["license_review", "auto_checked", "sampled_for_review", "quarantined"];

type ViewTip = { text: string; roles?: string[] };

const viewHelpContent: Partial<Record<ActiveView, { purpose: string; tips: ViewTip[] }>> = {
  sources: {
    purpose: "Tüm veri kaynaklarının kataloğu. Her satırdaki “Sıradaki kapı” sütunu, o kaynak için şimdi ne beklendiğini söyler.",
    tips: [
      { text: "Satıra tıklayınca sağda detay paneli açılır: kapılar, örnekler, dosya yükleme ve geçmiş." },
      { text: "“Yeni kaynak” ile kayıt açıp dosya yükleyebilirsiniz.", roles: ["admin", "data_manager"] },
      { text: "Metadata ve hak bilgisini düzenleyebilirsiniz; onay kararı bu ekranda değil İnceleme'dedir.", roles: ["editor"] },
      { text: "Bu ekranda yalnız görüntüler ve detay panelinden karar verirsiniz; kaynak açamazsınız.", roles: ["moderator", "expert_reviewer"] },
    ],
  },
  review: {
    purpose: "Karar bekleyen kaynakların öncelik sıralı kuyruğu. Belge kararı verebilmek için önce kendinize bir iş paketi alırsınız; tüm örnekler karara bağlanınca kaynak kararı verilir.",
    tips: [
      { text: "Kaynağı açıp “Güvenli paket al” ile 10-20 belgelik paketinizi alın; belgeler 15 dakika yalnız size atanır ve açık sekme paketi otomatik yeniler.", roles: ["admin", "moderator", "expert_reviewer"] },
      { text: "Yalnız kendi paketinizdeki belgelerde karar verebilirsiniz — başka inceleyicinin belgesi size dağıtılmaz, çakışma olmaz.", roles: ["admin", "moderator", "expert_reviewer"] },
      { text: "Paketinizdeki belgeleri seçip toplu kararla tek seferde puanlayabilirsiniz; şüpheli belgeyi ayrı açıp reddedin." },
      { text: "Ara verecekseniz “Paketi bırak” deyin; sekme kapansa bile belgeler en geç 15 dakikada havuza döner.", roles: ["admin", "moderator", "expert_reviewer"] },
      { text: "Kendi yüklediğiniz kaynağı onaylayamazsınız (bağımsız inceleme kuralı)." },
      { text: "“Onayla” pasifse detay panelindeki kapı listesi eksik koşulu gösterir: incelenmemiş örnek, hak durumu, PII veya tekrar." },
    ],
  },
  similarity: {
    purpose: "Yakın-tekrar aday çiftlerinin körlemeli etiketlenmesi: diğer inceleyicilerin kararını göremezsiniz, onlar da sizinkini göremez.",
    tips: [
      { text: "Yalnız iki metni karşılaştırın: aynı mı, türev mi, ilgisiz mi? “Doğru cevabı” tahmin etmeye çalışmayın; dürüst etiket, eşik kararının girdisidir." },
    ],
  },
  releases: {
    purpose: "Taslak ve frozen release'ler. Frozen release asla değişmez; düzeltme yeni release olarak çıkar.",
    tips: [
      { text: "Aynı amaçtaki onaylı kaynaklardan taslak oluşturabilirsiniz.", roles: ["admin", "data_manager"] },
      { text: "Freeze yalnız admin yetkisidir; freeze sırasında tüm kapılar yeniden koşar.", roles: ["admin"] },
      { text: "Manifest ve export dosyalarını indirip SHA256 ile doğrulayabilirsiniz." },
    ],
  },
  jobs: {
    purpose: "Arka plan işlerinin durumu ve canlı ilerlemesi.",
    tips: [
      { text: "İşler uzun süre “queued” durumunda kalıyorsa worker servisi çalışmıyor olabilir." },
      { text: "Büyük dosyalarda ilerleme 64 MiB aralıklarla güncellenir; sayfa kendini yeniler." },
    ],
  },
  users: {
    purpose: "Kullanıcı hesapları ve rolleri (yalnız admin görür).",
    tips: [
      { text: "Rolü veya durumu değişen kullanıcının açık oturumları otomatik olarak düşer." },
      { text: "Son aktif admin devre dışı bırakılamaz; kendi hesabınızın admin rolünü kaldıramazsınız." },
    ],
  },
  contribute: {
    purpose: "Katkı kuyruğu: kendi ürettiğiniz soru-cevap çiftleri ve metinler burada havuzda birikir, kaynağa demetlenir ve normal kalite kapılarından geçer.",
    tips: [
      { text: "Görev tipini seçin, metninizi yazın ve kullanım şartını onaylayıp gönderin; katkınız listenizde birikir.", roles: ["contributor", "admin"] },
      { text: "Demetlenmemiş katkınızı geri çekebilirsiniz; demetlenen katkı değişmez kaynağın parçasıdır.", roles: ["contributor", "admin"] },
      { text: "Yalnız kendi ürettiğiniz metni gönderin; başka yerden kopyalanan içerik hak/lisans kapısına takılır.", roles: ["contributor"] },
      { text: "“Kaynağa demetle” bekleyen havuzu tek kaynağa yazar: soru-cevap → instruction, serbest metin → pretrain.", roles: ["admin", "data_manager"] },
      { text: "Demetlenen kaynak PII, tekrar ve örneklem incelemesinden geçer; katkıcılar kendi metnini inceleyemez.", roles: ["admin", "data_manager"] },
    ],
  },
};

function WelcomeTip({ user, onNavigate }: { user: User; onNavigate: (view: ActiveView) => void }) {
  const storageKey = `derlem-welcome-dismissed-${user.id}`;
  const [dismissed, setDismissed] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDismissed(window.localStorage.getItem(storageKey) === "1");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [storageKey]);
  if (dismissed) return null;
  const primaryRole = user.roles.find((role) => roleInfoByRole[role]);
  const info = primaryRole ? roleInfoByRole[primaryRole] : undefined;
  function dismiss() {
    window.localStorage.setItem(storageKey, "1");
    setDismissed(true);
  }
  return (
    <section className="welcome-tip" aria-label="Hoş geldiniz">
      <div className="welcome-tip-body">
        <strong>Derlem’e hoş geldiniz.</strong>
        <p>
          Derlem, LLM eğitiminde kullanılacak metnin <em>hakları belli</em>, <em>kalitesi insan
          onaylı</em> ve <em>tekrarı ayıklanmış</em> biçimde toplandığı veri atölyesidir. Kimse
          buraya elle metin yazmaz: dosyalar alınır, otomatik kapılardan geçer ve insan onayıyla
          eğitime hazır değişmez paketlere dönüşür. Bu zincirdeki her karar size güvenilir.
        </p>
        {info && (
          <>
            <p className="welcome-tip-role">
              <strong>Rolünüz:</strong> {info.title} — {info.who.toLocaleLowerCase("tr-TR")}
            </p>
            <ol className="welcome-tip-steps">
              {info.firstSteps.map((step) => <li key={step}>{step}</li>)}
            </ol>
          </>
        )}
        <p className="welcome-tip-hint">
          Takıldığınız her ekranda üstteki <strong>“Bu ekranda ne yapabilirim?”</strong> kutusunu
          açın; akışın tamamı soldaki Rehber’dedir.
        </p>
        <div className="welcome-tip-actions">
          {info && info.start.view !== "guide" && (
            <button type="button" className="primary-button" onClick={() => { dismiss(); onNavigate(info.start.view); }}>
              <ArrowRight size={16} aria-hidden="true" /> {info.start.label}
            </button>
          )}
          <button type="button" className={info && info.start.view !== "guide" ? "secondary-button" : "primary-button"} onClick={() => { dismiss(); onNavigate("guide"); }}>
            <BookOpen size={16} aria-hidden="true" /> Rehber’i aç
          </button>
          <button type="button" className="text-button" onClick={dismiss}>Anladım, kapat</button>
        </div>
      </div>
      <button type="button" className="icon-button compact" title="Kapat" onClick={dismiss}>
        <X size={16} aria-hidden="true" />
      </button>
    </section>
  );
}

function ViewHelp({ view, user }: { view: ActiveView; user: User }) {
  const help = viewHelpContent[view];
  if (!help) return null;
  const tips = help.tips.filter((tip) => !tip.roles || hasAnyRole(user, tip.roles));
  return (
    <details className="view-help">
      <summary><Info size={15} aria-hidden="true" /> Bu ekranda ne yapabilirim?</summary>
      <p>{help.purpose}</p>
      <ul>
        {tips.map((tip) => <li key={tip.text}>{tip.text}</li>)}
      </ul>
      <p className="view-help-more">Akışın tamamı ve rolünüzün tüm yetkileri için sol menüdeki Rehber sekmesine bakın.</p>
    </details>
  );
}

export function DerlemApp() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [sources, setSources] = useState<Source[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Source | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ActiveView>("sources");
  const createDialog = useRef<HTMLDialogElement>(null);

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    try {
      const payload = await requestJSON<SourceList>("/api/sources?limit=200");
      setSources(payload.items);
      setSelected((current) =>
        current ? payload.items.find((source) => source.id === current.id) ?? null : null,
      );
    } catch (error) {
      setNotice(messageFrom(error));
    } finally {
      setLoadingSources(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const currentUser = await requestJSON<User>("/api/session/me");
        setUser(currentUser);
        setActiveView(defaultViewFor(currentUser));
        if (hasAnyRole(currentUser, sourceWorkspaceRoles)) {
          await loadSources();
        }
      } catch {
        setUser(null);
      } finally {
        setBooting(false);
      }
    })();
  }, [loadSources]);

  const filteredSources = useMemo(() => {
    const viewSources = activeView === "review"
      ? [...sources.filter((source) => reviewStatuses.includes(source.approval_status))]
        .sort((left, right) => reviewPriority(left) - reviewPriority(right) || Date.parse(right.created_at) - Date.parse(left.created_at))
      : sources;
    const normalized = query.trim().toLocaleLowerCase("tr-TR");
    if (!normalized) return viewSources;
    return viewSources.filter((source) =>
      [source.name, source.domain, source.language, source.license, source.source_type]
        .join(" ")
        .toLocaleLowerCase("tr-TR")
        .includes(normalized),
    );
  }, [activeView, query, sources]);

  if (booting) {
    return (
      <main className="centered-state">
        <LoaderCircle className="spin" aria-hidden="true" />
        <span>Derlem açılıyor</span>
      </main>
    );
  }

  if (!user) {
    return <Login onLogin={(loggedInUser) => {
      setUser(loggedInUser);
      setActiveView(defaultViewFor(loggedInUser));
      if (hasAnyRole(loggedInUser, sourceWorkspaceRoles)) {
        void loadSources();
      } else {
        setSources([]);
      }
    }} />;
  }

  const clearedCount = sources.filter((source) => source.rights_status === "cleared").length;
  const ingestedCount = sources.filter((source) => source.object_sha256).length;
  const reviewQueueSources = sources.filter((source) => reviewStatuses.includes(source.approval_status));
  const pendingSampleCount = sources.reduce((total, source) => total + Math.max(source.sampled_document_count - source.reviewed_document_count, 0), 0);
  const flaggedSampleCount = sources.reduce((total, source) => total + source.flagged_document_count, 0);
  const approvalReadyCount = sources.filter((source) => nextStepFor(source).key === "source_approval").length;
  const canCreateSource = user.roles.some((role) => ["admin", "data_manager"].includes(role));
  const canAccessSources = hasAnyRole(user, sourceWorkspaceRoles);
  const canAccessReview = hasAnyRole(user, reviewerRoles);
  const canAccessReleases = hasAnyRole(user, releaseRoles);
  const canAccessJobs = hasAnyRole(user, jobRoles);
  const canAccessContributions = hasAnyRole(user, contributionViewRoles);

  async function logout() {
    const response = await fetch("/api/session/logout", { method: "POST" });
    if (!response.ok) {
      setNotice("Oturum sunucuda kapatılamadı. Lütfen yeniden deneyin.");
      return;
    }
    setUser(null);
    setSources([]);
  }

  async function createSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    try {
      const source = await requestJSON<Source>("/api/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      createDialog.current?.close();
      setSources((current) => [source, ...current]);
      setSelected(source);
      setNotice("Kaynak kaydedildi.");
    } catch (error) {
      setNotice(messageFrom(error));
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Database size={22} strokeWidth={1.8} aria-hidden="true" />
          <span>Derlem</span>
        </div>
        <nav aria-label="Ana menü">
          {canAccessSources && (
            <button aria-label="Kaynaklar" aria-pressed={activeView === "sources"} className={`nav-item${activeView === "sources" ? " active" : ""}`} type="button" onClick={() => { setActiveView("sources"); setSelected(null); }}>
              <Library size={18} aria-hidden="true" />
              Kaynaklar
              <span>{sources.length}</span>
            </button>
          )}
          {canAccessReview && (
            <button aria-label="İnceleme" aria-pressed={activeView === "review"} className={`nav-item${activeView === "review" ? " active" : ""}`} type="button" onClick={() => { setActiveView("review"); setSelected(null); }}>
              <ClipboardCheck size={18} aria-hidden="true" />
              İnceleme
              <span>{sources.filter((source) => reviewStatuses.includes(source.approval_status)).length}</span>
            </button>
          )}
          {canAccessReview && (
            <button aria-label="Benzerlik" aria-pressed={activeView === "similarity"} className={`nav-item${activeView === "similarity" ? " active" : ""}`} type="button" onClick={() => { setActiveView("similarity"); setSelected(null); }}>
              <GitCompareArrows size={18} aria-hidden="true" />
              Benzerlik
              <span>›</span>
            </button>
          )}
          {canAccessReleases && (
            <button aria-label="Sürümler" aria-pressed={activeView === "releases"} className={`nav-item${activeView === "releases" ? " active" : ""}`} type="button" onClick={() => { setActiveView("releases"); setSelected(null); }}>
              <PackageCheck size={18} aria-hidden="true" />
              Sürümler
              <span>›</span>
            </button>
          )}
          {canAccessJobs && (
            <button aria-label="İşler" aria-pressed={activeView === "jobs"} className={`nav-item${activeView === "jobs" ? " active" : ""}`} type="button" onClick={() => { setActiveView("jobs"); setSelected(null); }}>
              <ListTodo size={18} aria-hidden="true" />
              İşler
              <span>›</span>
            </button>
          )}
          {canAccessContributions && (
            <button aria-label="Katkılar" aria-pressed={activeView === "contribute"} className={`nav-item${activeView === "contribute" ? " active" : ""}`} type="button" onClick={() => { setActiveView("contribute"); setSelected(null); }}>
              <PenLine size={18} aria-hidden="true" />
              Katkılar
              <span>›</span>
            </button>
          )}
          {user.roles.includes("admin") && (
            <button aria-label="Kullanıcılar" aria-pressed={activeView === "users"} className={`nav-item${activeView === "users" ? " active" : ""}`} type="button" onClick={() => { setActiveView("users"); setSelected(null); }}>
              <UsersRound size={18} aria-hidden="true" />
              Kullanıcılar
              <span>›</span>
            </button>
          )}
          <button aria-label="Rehber" aria-pressed={activeView === "guide"} className={`nav-item${activeView === "guide" ? " active" : ""}`} type="button" onClick={() => { setActiveView("guide"); setSelected(null); }}>
            <BookOpen size={18} aria-hidden="true" />
            Rehber
            <span>›</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <div className="user-block">
            <span>{user.email}</span>
            <small>{user.roles.join(", ")}</small>
          </div>
          <button className="icon-button" type="button" title="Oturumu kapat" onClick={() => void logout()}>
            <LogOut size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="sidebar-version" title={versionLabel}>
          <span>Derlem · v{APP_VERSION}</span>
          <span>build {APP_BUILD}</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="page-header">
          <div>
            <p className="eyebrow">{viewHeading(activeView).eyebrow}</p>
            <h1>{viewHeading(activeView).title}</h1>
          </div>
          {canCreateSource && (activeView === "sources" || activeView === "review") && (
            <button className="primary-button" type="button" onClick={() => createDialog.current?.showModal()}>
              <Plus size={18} aria-hidden="true" />Yeni kaynak
            </button>
          )}
        </header>

        <WelcomeTip user={user} onNavigate={(view) => { setActiveView(view); setSelected(null); }} />

        <ViewHelp view={activeView} user={user} />

        {(activeView === "sources" || activeView === "review") && <section className="summary-strip" aria-label={activeView === "review" ? "İnceleme özeti" : "Kaynak özeti"}>
          {activeView === "review" ? (
            <>
              <Summary icon={<ClipboardCheck />} label="Kuyruktaki kaynak" value={reviewQueueSources.length} tone="blue" />
              <Summary icon={<FileText />} label="Bekleyen örnek" value={pendingSampleCount} />
              <Summary icon={<AlertTriangle />} label="İşaretli örnek" value={flaggedSampleCount} tone="red" />
              <Summary icon={<CheckCircle2 />} label="Onaya hazır" value={approvalReadyCount} tone="green" />
            </>
          ) : (
            <>
              <Summary icon={<FileText />} label="Toplam" value={sources.length} />
              <Summary icon={<ShieldCheck />} label="Hakları temiz" value={clearedCount} tone="green" />
              <Summary icon={<CheckCircle2 />} label="Dosyası alınan" value={ingestedCount} tone="blue" />
            </>
          )}
        </section>}

        {notice && (
          <div className="notice" role="status">
            <span>{notice}</span>
            <button className="icon-button compact" type="button" title="Bildirimi kapat" onClick={() => setNotice(null)}>
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        )}

        {activeView === "guide" ? (
          <GuidePanel user={user} />
        ) : activeView === "contribute" ? <ContributionsPanel user={user} onNotice={setNotice} onBundled={() => void loadSources()} /> : activeView === "users" ? <UsersPanel currentUserID={user.id} onNotice={setNotice} /> : activeView === "jobs" ? <JobsPanel onNotice={setNotice} /> : activeView === "releases" ? <ReleasePanel sources={sources} user={user} onNotice={setNotice} /> : activeView === "similarity" ? <SimilarityReviewPanel user={user} onNotice={setNotice} /> : <section className={`catalog-layout${selected ? " with-inspector" : ""}`}>
          <div className="catalog-panel">
            <div className="table-toolbar">
              <label className="search-field">
                <Search size={17} aria-hidden="true" />
                <span className="sr-only">Kaynak ara</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Kaynak ara" />
              </label>
              <button className="icon-button" type="button" title="Kaynakları yenile" onClick={() => void loadSources()}>
                <RefreshCw className={loadingSources ? "spin" : ""} size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Kaynak</th>
                    <th>Amaç</th>
                    <th>Hak durumu</th>
                    <th>İşlem durumu</th>
                    <th>Sıradaki kapı</th>
                    <th>PII</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSources.map((source) => (
                    <tr key={source.id} className={selected?.id === source.id ? "selected-row" : undefined}>
                      <td>
                        <button className="source-link" type="button" onClick={() => setSelected(source)}>
                          <strong>{source.name}</strong>
                          <span>{source.domain}</span>
                        </button>
                      </td>
                      <td><span className="purpose-label">{purposeLabels[source.content_purpose]}</span></td>
                      <td><Status value={source.rights_status} /></td>
                      <td>{statusLabels[source.approval_status] ?? source.approval_status}</td>
                      <td><NextStep source={source} /></td>
                      <td><span className={`pii-status ${source.pii_status}`}>{source.pii_status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!loadingSources && filteredSources.length === 0 && (
                <div className="empty-state">
                  <FilePlus2 size={24} aria-hidden="true" />
                  <p>{sources.length === 0 ? "Henüz kaynak kaydı yok." : activeView === "review" && !query ? "İnceleme bekleyen kaynak yok." : "Aramayla eşleşen kaynak yok."}</p>
                </div>
              )}
            </div>
          </div>

          {selected && <SourceInspector source={selected} user={user} onClose={() => setSelected(null)} onNotice={setNotice} onRefresh={loadSources} onChanged={(updated) => { setSelected(updated); setSources((current) => current.map((source) => source.id === updated.id ? updated : source)); }} />}
        </section>}
      </main>

      <dialog ref={createDialog} className="source-dialog">
        <form onSubmit={createSource}>
          <div className="dialog-header">
            <div>
              <span>Kaynak kataloğu</span>
              <h2>Yeni kaynak</h2>
            </div>
            <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => createDialog.current?.close()}>
              <X size={19} aria-hidden="true" />
            </button>
          </div>
          <div className="form-grid">
            <label className="full-width">Kaynak adı<input name="name" required maxLength={240} /></label>
            <label>Kaynak tipi<input name="source_type" placeholder="web_corpus" required /></label>
            <label>
              İçerik amacı
              <select name="content_purpose" defaultValue="pretrain" required>
                {Object.entries(purposeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>Lisans<input name="license" placeholder="CC-BY-4.0" required /></label>
            <label>
              Hak durumu
              <select name="rights_status" defaultValue="unknown" required>
                <option value="unknown">Bilinmiyor</option>
                <option value="cleared">Temizlendi</option>
                <option value="restricted">Kısıtlı</option>
                <option value="blocked">Engelli</option>
              </select>
            </label>
            <label>
              Dil
              <input name="language" defaultValue="tr" list="language-suggestions" required />
              <datalist id="language-suggestions">
                {[
                  ["tr", "Türkçe"], ["en", "İngilizce"], ["ar", "Arapça"], ["de", "Almanca"],
                  ["fr", "Fransızca"], ["es", "İspanyolca"], ["ru", "Rusça"], ["fa", "Farsça"],
                  ["ku", "Kürtçe"], ["az", "Azerbaycan Türkçesi"], ["multi", "Çok dilli"],
                ].map(([code, label]) => <option key={code} value={code}>{label}</option>)}
              </datalist>
            </label>
            <label>
              Alan
              <input name="domain" placeholder="genel" list="domain-suggestions" required />
              <datalist id="domain-suggestions">
                {["bilisim", "biyoloji", "cografya", "dil", "din", "edebiyat", "egitim", "ekonomi", "felsefe", "fizik", "hukuk", "kimya", "kultur", "matematik", "muhendislik", "sosyal", "spor", "tarih", "tarim", "tip", "yurttaslik", "mixed", "genel"].map((value) => <option key={value} value={value} />)}
              </datalist>
            </label>
            <label className="full-width">Kaynak URL’si<input name="source_url" type="url" /></label>
            <label className="full-width">Lisans kanıtı<input name="license_evidence_ref" /></label>
            <label className="full-width">Köken bilgisi<input name="lineage_ref" placeholder="Dosya yolu, URL veya kayıt referansı" required /></label>
          </div>
          <div className="dialog-actions">
            <button className="text-button" type="button" onClick={() => createDialog.current?.close()}>İptal</button>
            <button className="primary-button" type="submit">Kaynağı kaydet</button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const localEmail = process.env.NEXT_PUBLIC_LOCAL_LOGIN_EMAIL?.trim();
  const localPassword = process.env.NEXT_PUBLIC_LOCAL_LOGIN_PASSWORD;
  const localAccounts = parseLocalAccounts(process.env.NEXT_PUBLIC_LOCAL_TEST_ACCOUNTS);
  const fallbackAccounts = localEmail && localPassword
    ? [{ label: "admin", email: localEmail, password: localPassword }]
    : [];
  const accounts = localAccounts.length > 0 ? localAccounts : fallbackAccounts;
  const [email, setEmail] = useState(accounts[0]?.email ?? "");
  const [password, setPassword] = useState(accounts[0]?.password ?? "");
  const helpDialog = useRef<HTMLDialogElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = await requestJSON<{ user: User }>("/api/session/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      onLogin(payload.user);
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-topbar">
          <div className="login-brand"><Database size={28} aria-hidden="true" /><span>Derlem</span></div>
          <button type="button" className="login-help-button" onClick={() => helpDialog.current?.showModal()}>
            <HelpCircle size={16} aria-hidden="true" /> Kullanıcı tipleri
          </button>
        </div>
        <h1>Veri atölyesine giriş</h1>
        {accounts.length > 0 && (
          <div className="local-credentials" aria-label="Yerel giriş bilgileri">
            <span>Yerel test hesapları</span>
            <div className="local-account-list">
              {accounts.map((account) => (
                <button
                  key={account.email}
                  className="local-account-card"
                  type="button"
                  aria-pressed={email === account.email}
                  onClick={() => { setEmail(account.email); setPassword(account.password); setError(null); }}
                >
                  <strong>{account.label}</strong>
                  <span>{account.email}</span>
                  <code>{account.password}</code>
                  {accountHints[account.label] && <em>{accountHints[account.label]}</em>}
                </button>
              ))}
            </div>
          </div>
        )}
        <form onSubmit={submit}>
          <label>E-posta<input name="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required autoFocus /></label>
          <label>Parola<input name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button login-button" type="submit" disabled={submitting}>
            {submitting ? <LoaderCircle className="spin" size={18} /> : <LogIn size={18} />}
            Giriş yap
          </button>
        </form>
        <p className="login-version" title={versionLabel}>{versionLabel}</p>

        <dialog ref={helpDialog} className="role-help-dialog" aria-label="Kullanıcı tipleri ve yardım">
          <div className="role-help-head">
            <h2><HelpCircle size={19} aria-hidden="true" /> Kullanıcı tipleri</h2>
            <button type="button" className="icon-button" title="Kapat" onClick={() => helpDialog.current?.close()}>
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          <p className="role-help-intro">
            Derlem bir veri atölyesidir: hazır metin dosyaları sisteme alınır, otomatik kalite
            kapılarından geçirilir, insan incelemesiyle onaylanır ve eğitime hazır değişmez
            paketler üretilir. Her rol bu zincirin bir halkasıdır — aşağıda her kullanıcı tipinin
            kim olduğu ve ne iş yaptığı açıklanır.
          </p>
          <ul className="role-help-list">
            {ROLE_INFO.map((info) => (
              <li className="role-help-item" key={info.role}>
                <div className="role-help-title">
                  <strong>{info.title}</strong>
                  <span>{info.who}</span>
                </div>
                <ul>
                  {info.duties.map((duty) => <li key={duty}>{duty}</li>)}
                </ul>
              </li>
            ))}
          </ul>
          <form method="dialog" className="role-help-actions">
            <button type="submit" className="primary-button">Kapat</button>
          </form>
        </dialog>
      </section>
    </main>
  );
}

function parseLocalAccounts(value: string | undefined) {
  return (value ?? "")
    .split(";")
    .map((record) => record.trim())
    .filter(Boolean)
    .map((record) => {
      const [label = "", email = "", password = ""] = record.split("|").map((part) => part.trim());
      return { label, email, password };
    })
    .filter((account) => account.label && account.email && account.password);
}

function hasAnyRole(user: User, allowedRoles: string[]) {
  return user.roles.some((role) => allowedRoles.includes(role));
}

function defaultViewFor(user: User): ActiveView {
  // Yönetici ve veri yöneticisi katalogdan, inceleyici doğrudan işinin
  // başından (İnceleme), katkıcı Katkılar'dan başlar; ilk oturumda "şimdi
  // ne yapacağım" sorusu ekran seçimiyle de cevaplanmış olur.
  if (hasAnyRole(user, ["admin", "data_manager"])) return "sources";
  if (hasAnyRole(user, ["moderator", "expert_reviewer"])) return "review";
  if (hasAnyRole(user, sourceWorkspaceRoles)) return "sources";
  if (hasAnyRole(user, ["contributor"])) return "contribute";
  if (hasAnyRole(user, releaseRoles)) return "releases";
  return "guide";
}

function viewHeading(view: ActiveView) {
  const headings: Record<ActiveView, { eyebrow: string; title: string }> = {
    sources: { eyebrow: "Kaynak kataloğu", title: "Veri kaynakları" },
    review: { eyebrow: "Moderasyon", title: "İnceleme kuyruğu" },
    similarity: { eyebrow: "Kalibrasyon", title: "Benzerlik incelemesi" },
    releases: { eyebrow: "Release Builder", title: "Sürümler" },
    jobs: { eyebrow: "Worker kuyruğu", title: "Arka plan işleri" },
    users: { eyebrow: "Yönetim", title: "Kullanıcılar" },
    contribute: { eyebrow: "Katkı kuyruğu", title: "Katkılar" },
    guide: { eyebrow: "Yardım", title: "Derlem rehberi" },
  };
  return headings[view];
}

function Summary({ icon, label, value, tone = "neutral" }: { icon: React.ReactElement; label: string; value: number; tone?: string }) {
  return <div className={`summary-item ${tone}`}>{icon}<span>{label}</span><strong>{value.toLocaleString("tr-TR")}</strong></div>;
}

function Status({ value }: { value: string }) {
  const labels: Record<string, string> = { unknown: "Bilinmiyor", cleared: "Temiz", restricted: "Kısıtlı", blocked: "Engelli" };
  return <span className={`status ${value}`}>{labels[value] ?? value}</span>;
}

function NextStep({ source }: { source: Source }) {
  const step = nextStepFor(source);
  return <span className={`next-step ${step.tone}`}>{step.label}</span>;
}

function nextStepFor(source: Source) {
  if (!source.object_sha256) return { key: "file", label: "Dosya bekliyor", tone: "neutral" };
  if (source.rights_status !== "cleared") return { key: "rights", label: "Hak incelemesi", tone: "warning" };
  if (!source.license_evidence_ref) return { key: "license", label: "Lisans kanıtı", tone: "warning" };
  if (source.pii_status !== "clear") return { key: "pii", label: "PII kapısı", tone: "danger" };
  if (source.duplicate_status !== "unique") return { key: "exact_dedup", label: "Exact dedup", tone: "danger" };
  if (source.normalized_dedup_status !== "unique") return { key: "normalized_dedup", label: "Normalize dedup", tone: "danger" };
  if (source.document_sampling_status !== "sampled") return { key: "sampling", label: "Örnekleme", tone: "warning" };
  if (source.flagged_document_count > 0) return { key: "flagged_sample", label: "İşaretli örnek", tone: "danger" };
  if (
    source.sampled_document_count === 0
    || source.reviewed_document_count !== source.sampled_document_count
    || source.approved_document_count !== source.sampled_document_count
  ) {
    return {
      key: "sample_review",
      label: `Örnek ${source.approved_document_count.toLocaleString("tr-TR")}/${source.sampled_document_count.toLocaleString("tr-TR")}`,
      tone: "warning",
    };
  }
  if (source.approval_status !== "approved_source") return { key: "source_approval", label: "Kaynak onayı", tone: "ready" };
  return { key: "approved", label: "Onaylı", tone: "ready" };
}

function reviewPriority(source: Source) {
  const step = nextStepFor(source);
  const priorities: Record<string, number> = {
    sample_review: 0,
    source_approval: 1,
    flagged_sample: 2,
    rights: 3,
    license: 3,
    pii: 4,
    exact_dedup: 4,
    normalized_dedup: 4,
    sampling: 5,
    file: 6,
    approved: 7,
  };
  return priorities[step.key] ?? 8;
}
