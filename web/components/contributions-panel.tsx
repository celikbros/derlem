"use client";

import { CircleHelp, PackagePlus, PenLine, RefreshCw, Trash2, X } from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";

import { messageFrom, requestJSON } from "@/lib/client-api";
import {
  contributionDataOrigins,
  contributionTaskTypes,
  dataOriginSpec,
  taskTypeLabel,
  taskTypeSpec,
  type ContributionPayloadFieldSpec,
} from "@/lib/contribution-task-types";
import type { Contribution, PendingContribution, User } from "@/lib/types";

const statusChips: Record<string, { label: string; tone: string }> = {
  submitted: { label: "Havuzda bekliyor", tone: "unknown" },
  withdrawn: { label: "Geri çekildi", tone: "blocked" },
  bundled: { label: "Kaynağa demetlendi", tone: "cleared" },
};

const defaultTaskType = contributionTaskTypes[0]?.name ?? "";

// Genel alanların yardım metinleri. Tipe özel metinler Go kayıt defterindedir
// (internal/domain/contribution.go → contribution-task-types.json).
const domainHint =
  "Katkının konusu; tek kelime, küçük harfle (örn. fizik, tarih, hukuk). Emin değilseniz boş bırakın: " +
  "veri yöneticisi demetlerken konuyu belirler. Aynı konuyu hep aynı yazın; daha önce kullandıklarınız öneri olarak çıkar.";
const modelIDHint =
  "Cevabı üreten yapay zekânın adı; biliyorsanız sürümüyle birlikte. Kaydın hangi modelden geldiği bununla izlenir.";
const bundleDomainHint =
  "Oluşacak kaynağın konusu. Seçilen tipte bu konuyla etiketlenmiş katkılar ve konusu boş bırakılmış katkılar demete girer; " +
  "başka konudaki katkılar havuzda kalır.";
const bundleLanguageHint =
  "Katkıların dili (örn. tr). Kişisel veri taraması şu an yalnız Türkçe metni değerlendirir.";
const bundleNameHint =
  "Kaynaklar listesinde görünecek ad. Konu ve tarih içermesi sonradan bulmayı kolaylaştırır.";

function defaultOriginFor(taskType: string) {
  return taskTypeSpec(taskType)?.default_data_origin || "human";
}

function sameDomain(left: string, right: string) {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

function preview(value: string, limit = 140) {
  const flattened = value.replace(/\s+/g, " ").trim();
  return flattened.length > limit ? `${flattened.slice(0, limit)}…` : flattened;
}

// Özet: soru, (varsa) metinle karşılaştırılan payload alanı ve metin. Düzeltme
// çiftinde "soru — orijinal cevap → düzeltilmiş cevap" okunur.
function contributionSummary(item: Pick<Contribution, "task_type" | "prompt" | "body" | "payload">) {
  const distinctKey = taskTypeSpec(item.task_type)?.distinct_from_body;
  const original = distinctKey ? item.payload?.[distinctKey] : "";
  const answer = original ? `${original} → ${item.body}` : item.body;
  return preview(item.prompt ? `${item.prompt} — ${answer}` : answer);
}

/**
 * Etiket + yardım düğmesi + (açılır) açıklama + kontrol. Düğme <label> içine
 * konmaz: etiketlenebilir ilk öğe olarak etiketi kutudan çalardı. Açıklama kapalıyken
 * de aria-describedby ile ekran okuyucuya iletilir.
 */
function FormField({ label, hint, optional = false, fullWidth = false, children }: {
  label: string;
  hint?: string;
  optional?: boolean;
  fullWidth?: boolean;
  children: (controlId: string, describedBy: string | undefined) => ReactNode;
}) {
  const controlId = useId();
  const hintId = `${controlId}-hint`;
  const [open, setOpen] = useState(false);
  return (
    <div className={`form-field${fullWidth ? " full-width" : ""}`}>
      <div className="form-field-label">
        <label htmlFor={controlId}>
          {label}
          {optional && <span className="optional-mark"> (opsiyonel)</span>}
        </label>
        {hint && (
          <button
            className="field-help-button"
            type="button"
            aria-expanded={open}
            aria-controls={hintId}
            aria-label={`${label}: bu alan ne işe yarar?`}
            title="Bu alan ne işe yarar?"
            onClick={() => setOpen((value) => !value)}
          >
            <CircleHelp size={15} aria-hidden="true" />
          </button>
        )}
      </div>
      {hint && <p id={hintId} className="field-hint" hidden={!open}>{hint}</p>}
      {children(controlId, hint ? hintId : undefined)}
    </div>
  );
}

function PayloadField({ field, fullWidth }: { field: ContributionPayloadFieldSpec; fullWidth: boolean }) {
  return (
    <FormField label={field.label} hint={field.hint} optional={!field.required} fullWidth={fullWidth}>
      {(id, describedBy) => (
        <textarea
          id={id}
          aria-describedby={describedBy}
          name={`payload.${field.key}`}
          rows={field.max_chars > 2000 ? 4 : 2}
          required={field.required}
          maxLength={field.max_chars}
          placeholder={field.placeholder}
        />
      )}
    </FormField>
  );
}

export function ContributionsPanel({ user, onNotice, onBundled }: {
  user: User;
  onNotice: (message: string) => void;
  onBundled?: () => void;
}) {
  const canContribute = user.roles.some((role) => role === "contributor" || role === "admin");
  const canManage = user.roles.some((role) => role === "admin" || role === "data_manager");

  const [mine, setMine] = useState<Contribution[]>([]);
  const [pending, setPending] = useState<PendingContribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [taskType, setTaskType] = useState(defaultTaskType);
  const [dataOrigin, setDataOrigin] = useState(defaultOriginFor(defaultTaskType));
  const [bundleTaskType, setBundleTaskType] = useState(defaultTaskType);
  const [bundleDomain, setBundleDomain] = useState("");
  const bundleDialog = useRef<HTMLDialogElement>(null);
  const domainListId = useId();
  const bundleDomainListId = useId();

  const spec = taskTypeSpec(taskType);
  const origin = dataOriginSpec(dataOrigin);
  const distinctField = spec?.payload.find((field) => field.key === spec.distinct_from_body);
  const otherFields = spec?.payload.filter((field) => field.key !== spec.distinct_from_body) ?? [];
  const originHint = [
    spec?.origin_hint,
    ...contributionDataOrigins.map((option) => `${option.label}: ${option.hint}`),
  ].filter(Boolean).join("\n");

  const load = useCallback(async () => {
    try {
      if (canContribute) {
        const payload = await requestJSON<{ items: Contribution[] }>("/api/contributions/mine");
        setMine(payload.items);
      }
      if (canManage) {
        const payload = await requestJSON<{ items: PendingContribution[] }>("/api/contributions");
        setPending(payload.items);
      }
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [canContribute, canManage, onNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function changeTaskType(next: string) {
    setTaskType(next);
    setDataOrigin(defaultOriginFor(next));
  }

  async function submitContribution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!spec) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    // Yalnız dolu payload alanları gönderilir; API boş isteğe bağlı alanı zaten atar.
    const payload: Record<string, string> = {};
    for (const field of spec.payload) {
      const value = String(data.get(`payload.${field.key}`) ?? "").trim();
      if (value) payload[field.key] = value;
    }
    setSaving(true);
    try {
      await requestJSON<Contribution>("/api/contributions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_type: spec.name,
          domain: String(data.get("domain") ?? ""),
          prompt: spec.prompt_forbidden ? "" : String(data.get("prompt") ?? ""),
          body: String(data.get("body") ?? ""),
          payload,
          data_origin: dataOrigin,
          model_id: origin?.requires_model_id ? String(data.get("model_id") ?? "") : "",
          accept_terms: data.get("accept_terms") === "on",
        }),
      });
      form.reset();
      setDataOrigin(defaultOriginFor(spec.name));
      onNotice("Katkınız havuza alındı. Demetlenene kadar geri çekebilirsiniz.");
      setLoading(true);
      await load();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSaving(false);
    }
  }

  async function withdrawContribution(id: string) {
    setSaving(true);
    try {
      await requestJSON<void>(`/api/contributions/${encodeURIComponent(id)}`, { method: "DELETE" });
      onNotice("Katkı geri çekildi.");
      setLoading(true);
      await load();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSaving(false);
    }
  }

  function openBundleDialog() {
    // Bekleyen katkısı olan ilk tip seçili gelir; boş tiple açılan pencere
    // "0 katkı" demetlemeye çalışırdı.
    const firstWithPending = contributionTaskTypes.find((type) => pending.some((item) => item.task_type === type.name));
    const nextType = firstWithPending?.name ?? defaultTaskType;
    setBundleTaskType(nextType);
    const domains = pendingDomains(nextType);
    setBundleDomain(domains.length === 1 ? domains[0].domain : "");
    bundleDialog.current?.showModal();
  }

  async function bundleContributions(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setSaving(true);
    try {
      const result = await requestJSON<{ source_id: string; job_id: string; count: number }>("/api/contribution-bundles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_type: bundleTaskType,
          name: String(data.get("name") ?? ""),
          language: String(data.get("language") ?? "tr"),
          domain: bundleDomain.trim(),
        }),
      });
      form.reset();
      setBundleDomain("");
      bundleDialog.current?.close();
      onNotice(`${result.count.toLocaleString("tr-TR")} katkı kaynağa demetlendi; normal kapılardan geçiyor.`);
      setLoading(true);
      await load();
      onBundled?.();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSaving(false);
    }
  }

  const pendingByType: Record<string, number> = Object.fromEntries(
    contributionTaskTypes.map((type) => [type.name, pending.filter((item) => item.task_type === type.name).length]),
  );

  // Seçilen tipteki bekleyen katkıların konuları (büyük/küçük harf farkı tek konu
  // sayılır; demet sorgusu da lower() ile eşleştirir).
  function pendingDomains(type: string) {
    const counts = new Map<string, { domain: string; count: number }>();
    for (const item of pending) {
      if (item.task_type !== type || !item.domain) continue;
      const key = item.domain.toLowerCase();
      const entry = counts.get(key);
      if (entry) entry.count += 1;
      else counts.set(key, { domain: item.domain, count: 1 });
    }
    return [...counts.values()].sort((left, right) => right.count - left.count || left.domain.localeCompare(right.domain, "tr"));
  }

  const bundleTypePending = pending.filter((item) => item.task_type === bundleTaskType);
  const bundleUnlabeled = bundleTypePending.filter((item) => !item.domain).length;
  const bundleLabeled = bundleDomain.trim()
    ? bundleTypePending.filter((item) => item.domain && sameDomain(item.domain, bundleDomain)).length
    : 0;
  const bundleOtherDomains = pendingDomains(bundleTaskType).filter((entry) => !sameDomain(entry.domain, bundleDomain));
  const myDomains = [...new Set(mine.map((item) => item.domain.trim().toLowerCase()).filter(Boolean))].sort((left, right) => left.localeCompare(right, "tr"));

  return (
    <section className="jobs-panel">
      {canContribute && (
        <form className="contribution-form" onSubmit={submitContribution} aria-label="Yeni katkı">
          <h3><PenLine size={16} aria-hidden="true" /> Yeni katkı</h3>
          <p className="muted-copy">
            Katkınız doğrudan corpus&apos;a girmez: havuzda birikir, kaynağa demetlenir ve kişisel veri,
            tekrar ve insan inceleme kontrollerinden geçer. Her alanın yanındaki
            <CircleHelp className="inline-icon" size={13} role="img" aria-label="yardım" /> düğmesi alanın ne istediğini açıklar.
          </p>
          <div className="form-grid">
            <FormField label="Görev tipi">
              {(id) => (
                <select id={id} name="task_type" value={taskType} onChange={(event) => changeTaskType(event.target.value)}>
                  {contributionTaskTypes.map((type) => (
                    <option key={type.name} value={type.name}>{type.label}</option>
                  ))}
                </select>
              )}
            </FormField>
            <FormField label="Alan" hint={domainHint} optional>
              {(id, describedBy) => (
                <>
                  <input id={id} aria-describedby={describedBy} name="domain" maxLength={100} placeholder="örn. fizik" list={domainListId} autoComplete="off" />
                  <datalist id={domainListId}>
                    {myDomains.map((value) => <option key={value} value={value} />)}
                  </datalist>
                </>
              )}
            </FormField>
            {spec?.description && (
              <p className="task-type-description full-width" aria-live="polite">{spec.description}</p>
            )}
            {spec && !spec.prompt_forbidden && (
              <FormField label={spec.prompt_label} hint={spec.prompt_hint} optional={!spec.prompt_required} fullWidth>
                {(id, describedBy) => (
                  <textarea
                    id={id}
                    aria-describedby={describedBy}
                    name="prompt"
                    rows={2}
                    required={spec.prompt_required}
                    maxLength={10000}
                    placeholder={spec.prompt_placeholder}
                  />
                )}
              </FormField>
            )}
            {spec && distinctField && (
              // Metinle karşılaştırılan alan (düzeltme çiftinde orijinal cevap) metnin
              // yanında durur: inceleyen de katkıcı da iki tarafı yan yana görür.
              <PayloadField field={distinctField} fullWidth={false} />
            )}
            {spec && (
              <FormField label={spec.body_label} hint={spec.body_hint} fullWidth={!distinctField}>
                {(id, describedBy) => (
                  <textarea
                    id={id}
                    aria-describedby={describedBy}
                    name="body"
                    rows={distinctField ? 4 : 6}
                    required
                    maxLength={100000}
                    placeholder={spec.body_placeholder}
                  />
                )}
              </FormField>
            )}
            {otherFields.map((field) => (
              <PayloadField key={field.key} field={field} fullWidth />
            ))}
            <FormField label="Köken" hint={originHint}>
              {(id, describedBy) => (
                <select id={id} aria-describedby={describedBy} name="data_origin" value={dataOrigin} onChange={(event) => setDataOrigin(event.target.value)}>
                  {contributionDataOrigins.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              )}
            </FormField>
            {origin?.requires_model_id && (
              <FormField label="Model adı" hint={modelIDHint}>
                {(id, describedBy) => (
                  <input id={id} aria-describedby={describedBy} name="model_id" required maxLength={200} placeholder="örn. modelin adı ve sürümü" />
                )}
              </FormField>
            )}
            <label className="full-width terms-check">
              <input type="checkbox" name="accept_terms" required />
              {origin?.requires_model_id
                ? "Bu model çıktısını gönderme hakkım var ve gözden geçirdim; eğitim amaçlı kullanım hakkını Derlem'e devrediyorum (şart: office-v1)."
                : "Bu metni kendim ürettim; eğitim amaçlı kullanım hakkını Derlem'e devrediyorum (şart: office-v1)."}
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={saving || !spec}>
            <PenLine size={16} aria-hidden="true" /> Katkıyı gönder
          </button>
        </form>
      )}

      <div className="table-toolbar">
        <div className="toolbar-title">
          {canManage ? (
            <>
              <span>Havuzda {pending.length.toLocaleString("tr-TR")} katkı bekliyor</span>
              <small>
                {contributionTaskTypes
                  .map((type) => `${(pendingByType[type.name] ?? 0).toLocaleString("tr-TR")} ${type.label.toLocaleLowerCase("tr-TR")}`)
                  .join(" · ")}
              </small>
            </>
          ) : (
            <>
              <span>{mine.length.toLocaleString("tr-TR")} katkınız var</span>
              <small>Demetlenmemiş katkılar geri çekilebilir</small>
            </>
          )}
        </div>
        <div className="toolbar-actions">
          <button className="icon-button" type="button" title="Listeyi yenile" onClick={() => { setLoading(true); void load(); }}>
            <RefreshCw className={loading ? "spin" : ""} size={18} aria-hidden="true" />
          </button>
          {canManage && (
            <button className="primary-button" type="button" disabled={pending.length === 0} onClick={openBundleDialog}>
              <PackagePlus size={18} aria-hidden="true" />Kaynağa demetle
            </button>
          )}
        </div>
      </div>

      {canManage && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Katkıcı</th><th>Tip</th><th>Alan</th><th>Özet</th><th>Tarih</th></tr>
            </thead>
            <tbody>
              {pending.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.contributor_name}</strong></td>
                  <td>{taskTypeLabel(item.task_type)}</td>
                  <td>{item.domain || "—"}</td>
                  <td>{contributionSummary(item)}</td>
                  <td>{new Date(item.created_at).toLocaleDateString("tr-TR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && pending.length === 0 && (
            <div className="empty-state"><p>Havuzda bekleyen katkı yok.</p></div>
          )}
        </div>
      )}

      {canContribute && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Tip</th><th>Özet</th><th>Durum</th><th>Tarih</th><th></th></tr>
            </thead>
            <tbody>
              {mine.map((item) => {
                const chip = statusChips[item.status] ?? { label: item.status, tone: "unknown" };
                return (
                  <tr key={item.id}>
                    <td>{taskTypeLabel(item.task_type)}</td>
                    <td>{contributionSummary(item)}</td>
                    <td><span className={`status ${chip.tone}`}>{chip.label}</span></td>
                    <td>{new Date(item.created_at).toLocaleDateString("tr-TR")}</td>
                    <td>
                      {item.status === "submitted" && (
                        <button className="icon-button compact" type="button" title="Katkıyı geri çek" disabled={saving} onClick={() => void withdrawContribution(item.id)}>
                          <Trash2 size={16} aria-hidden="true" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && mine.length === 0 && (
            <div className="empty-state"><p>Henüz katkınız yok. Yukarıdaki formla ilk katkınızı gönderin.</p></div>
          )}
        </div>
      )}

      <dialog ref={bundleDialog} className="source-dialog">
        <form onSubmit={bundleContributions}>
          <div className="dialog-header">
            <div>
              <span>Katkı havuzu</span>
              <h2>Kaynağa demetle</h2>
            </div>
            <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => bundleDialog.current?.close()}>
              <X size={19} aria-hidden="true" />
            </button>
          </div>
          <div className="form-grid">
            <FormField label="Görev tipi">
              {(id) => (
                <select id={id} name="task_type" value={bundleTaskType} onChange={(event) => setBundleTaskType(event.target.value)}>
                  {contributionTaskTypes.map((type) => (
                    <option key={type.name} value={type.name}>
                      {type.label} ({(pendingByType[type.name] ?? 0).toLocaleString("tr-TR")} bekliyor) → {type.content_purpose}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <FormField label="Dil" hint={bundleLanguageHint}>
              {(id, describedBy) => (
                <input id={id} aria-describedby={describedBy} name="language" defaultValue="tr" maxLength={20} />
              )}
            </FormField>
            <FormField label="Kaynak adı" hint={bundleNameHint} fullWidth>
              {(id, describedBy) => (
                <input id={id} aria-describedby={describedBy} name="name" required maxLength={200} placeholder="örn. katki_fizik_2026_09" />
              )}
            </FormField>
            <FormField label="Alan (konu)" hint={bundleDomainHint} fullWidth>
              {(id, describedBy) => (
                <>
                  <input
                    id={id}
                    aria-describedby={describedBy}
                    name="domain"
                    required
                    maxLength={100}
                    placeholder="örn. fizik"
                    list={bundleDomainListId}
                    autoComplete="off"
                    value={bundleDomain}
                    onChange={(event) => setBundleDomain(event.target.value)}
                  />
                  <datalist id={bundleDomainListId}>
                    {pendingDomains(bundleTaskType).map((entry) => <option key={entry.domain} value={entry.domain} />)}
                  </datalist>
                </>
              )}
            </FormField>
            <div className="bundle-preview full-width" aria-live="polite">
              {bundleDomain.trim() ? (
                <strong>
                  Bu seçimle {(bundleLabeled + bundleUnlabeled).toLocaleString("tr-TR")} katkı demetlenecek
                  {bundleUnlabeled > 0 && ` (${bundleUnlabeled.toLocaleString("tr-TR")} tanesi konusuz)`}.
                </strong>
              ) : (
                <strong>Konu yazın ya da aşağıdan seçin; kaç katkının demetleneceği burada görünür.</strong>
              )}
              {bundleOtherDomains.length > 0 && (
                <div className="bundle-domain-chips">
                  <span>Bu tipte başka konularda bekleyenler:</span>
                  {bundleOtherDomains.map((entry) => (
                    <button key={entry.domain} className="chip-button" type="button" onClick={() => setBundleDomain(entry.domain)}>
                      {entry.domain} ({entry.count.toLocaleString("tr-TR")})
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="muted-copy full-width">
              Katkılar tek kaynağa yazılır ve normal içe alma kontrollerinden geçer. Katkıcı kimliği dosyaya yazılmaz.
              Demeti yapan hesap (admin hariç) bu kaynağın örneklerini inceleyemez; incelemeyi başka bir inceleyici yapar.
            </p>
          </div>
          <div className="dialog-actions">
            <button className="text-button" type="button" onClick={() => bundleDialog.current?.close()}>İptal</button>
            <button className="primary-button" type="submit" disabled={saving || bundleLabeled + bundleUnlabeled === 0}>Demetle ve kuyruğa al</button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
