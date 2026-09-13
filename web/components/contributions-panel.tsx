"use client";

import { PackagePlus, PenLine, RefreshCw, Trash2, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

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

function PayloadField({ field, fullWidth }: { field: ContributionPayloadFieldSpec; fullWidth: boolean }) {
  return (
    <label className={fullWidth ? "full-width" : undefined}>
      {field.label}
      <textarea
        name={`payload.${field.key}`}
        rows={field.max_chars > 2000 ? 4 : 2}
        required={field.required}
        maxLength={field.max_chars}
      />
    </label>
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
  const [dataOrigin, setDataOrigin] = useState("human");
  const bundleDialog = useRef<HTMLDialogElement>(null);

  const spec = taskTypeSpec(taskType);
  const origin = dataOriginSpec(dataOrigin);
  const distinctField = spec?.payload.find((field) => field.key === spec.distinct_from_body);
  const otherFields = spec?.payload.filter((field) => field.key !== spec.distinct_from_body) ?? [];

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
      setDataOrigin("human");
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
          task_type: String(data.get("task_type") ?? defaultTaskType),
          name: String(data.get("name") ?? ""),
          language: String(data.get("language") ?? "tr"),
          domain: String(data.get("domain") ?? ""),
        }),
      });
      form.reset();
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

  return (
    <section className="jobs-panel">
      {canContribute && (
        <form className="contribution-form" onSubmit={submitContribution} aria-label="Yeni katkı">
          <h3><PenLine size={16} aria-hidden="true" /> Yeni katkı</h3>
          <p className="muted-copy">
            Katkınız doğrudan corpus&apos;a girmez: havuzda birikir, kaynağa demetlenir ve PII,
            tekrar ve insan inceleme kapılarından geçer.
          </p>
          <div className="form-grid">
            <label>
              Görev tipi
              <select name="task_type" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
                {contributionTaskTypes.map((type) => (
                  <option key={type.name} value={type.name}>{type.label}</option>
                ))}
              </select>
            </label>
            <label>Alan (opsiyonel)<input name="domain" maxLength={100} placeholder="fizik, hukuk, genel..." /></label>
            {spec && !spec.prompt_forbidden && (
              <label className="full-width">
                {spec.prompt_label}
                <textarea name="prompt" rows={2} required={spec.prompt_required} maxLength={10000} />
              </label>
            )}
            {spec && distinctField && (
              // Metinle karşılaştırılan alan (düzeltme çiftinde orijinal cevap) metnin
              // yanında durur: inceleyen de katkıcı da iki tarafı yan yana görür.
              <PayloadField field={distinctField} fullWidth={false} />
            )}
            {spec && (
              <label className={distinctField ? undefined : "full-width"}>
                {spec.body_label}
                <textarea name="body" rows={distinctField ? 4 : 6} required maxLength={100000} />
              </label>
            )}
            {otherFields.map((field) => (
              <PayloadField key={field.key} field={field} fullWidth />
            ))}
            <label>
              Köken
              <select name="data_origin" value={dataOrigin} onChange={(event) => setDataOrigin(event.target.value)}>
                {contributionDataOrigins.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {origin?.requires_model_id && (
              <label>Model adı<input name="model_id" required maxLength={200} placeholder="örn. model-x" /></label>
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
            <button className="primary-button" type="button" disabled={pending.length === 0} onClick={() => bundleDialog.current?.showModal()}>
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
            <label>
              Görev tipi
              <select name="task_type" defaultValue={defaultTaskType}>
                {contributionTaskTypes.map((type) => (
                  <option key={type.name} value={type.name}>
                    {type.label} ({(pendingByType[type.name] ?? 0).toLocaleString("tr-TR")} bekliyor) → {type.content_purpose}
                  </option>
                ))}
              </select>
            </label>
            <label>Dil<input name="language" defaultValue="tr" maxLength={20} /></label>
            <label className="full-width">Kaynak adı<input name="name" required maxLength={200} placeholder="ekip_katki_demeti_2026_07" /></label>
            <label className="full-width">Alan (domain)<input name="domain" required maxLength={100} placeholder="genel" /></label>
            <p className="muted-copy full-width">
              Seçilen tipteki, bu alan etiketli (ya da etiketsiz) bekleyen katkılar tek kaynağa yazılır ve
              normal ingest kapılarından geçer. Katkıcı kimliği dosyaya yazılmaz.
            </p>
          </div>
          <div className="dialog-actions">
            <button className="text-button" type="button" onClick={() => bundleDialog.current?.close()}>İptal</button>
            <button className="primary-button" type="submit" disabled={saving}>Demetle ve kuyruğa al</button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
