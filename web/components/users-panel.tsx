"use client";

import { KeyRound, Plus, RefreshCw, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { messageFrom, requestJSON } from "@/lib/client-api";
import type { UserAccount } from "@/lib/types";

const roleLabels: Record<string, string> = {
  admin: "Yönetici",
  data_manager: "Veri yöneticisi",
  editor: "Editör",
  moderator: "Moderatör",
  expert_reviewer: "Uzman inceleyici",
  contributor: "Katkıcı",
  consumer_team: "Tüketici ekip",
};

export function UsersPanel({ currentUserID, onNotice }: { currentUserID: string; onNotice: (message: string) => void }) {
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<UserAccount | null>(null);
  const createDialog = useRef<HTMLDialogElement>(null);
  const editDialog = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    try {
      const payload = await requestJSON<{ items: UserAccount[] }>("/api/users");
      setUsers(payload.items);
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setLoading(false);
    }
  }, [onNotice]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const roles = data.getAll("roles").map(String);
    setSaving(true);
    try {
      await requestJSON<UserAccount>("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: String(data.get("email") ?? ""),
          display_name: String(data.get("display_name") ?? ""),
          password: String(data.get("password") ?? ""),
          roles,
        }),
      });
      form.reset();
      createDialog.current?.close();
      onNotice("Kullanıcı oluşturuldu.");
      setLoading(true);
      await load();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSaving(false);
    }
  }

  async function updateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    const roles = data.getAll("roles").map(String);
    const newPassword = String(data.get("new_password") ?? "");
    const payload: Record<string, unknown> = {
      display_name: String(data.get("display_name") ?? ""),
      status: String(data.get("status") ?? "active"),
      roles,
    };
    if (newPassword) payload.new_password = newPassword;
    setSaving(true);
    try {
      await requestJSON<UserAccount>(`/api/users/${encodeURIComponent(selected.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      editDialog.current?.close();
      setSelected(null);
      onNotice("Kullanıcı güncellendi.");
      setLoading(true);
      await load();
    } catch (error) {
      onNotice(messageFrom(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="jobs-panel">
      <div className="table-toolbar">
        <div className="toolbar-title">
          <span>{users.length.toLocaleString("tr-TR")} kullanıcı</span>
          <small>Roller sunucu tarafında zorunlu tutulur; son aktif admin korunur</small>
        </div>
        <div className="toolbar-actions">
          <button className="icon-button" type="button" title="Kullanıcıları yenile" onClick={() => { setLoading(true); void load(); }}>
            <RefreshCw className={loading ? "spin" : ""} size={18} aria-hidden="true" />
          </button>
          <button className="primary-button" type="button" onClick={() => createDialog.current?.showModal()}>
            <Plus size={18} aria-hidden="true" />Yeni kullanıcı
          </button>
        </div>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>Kullanıcı</th><th>Roller</th><th>Durum</th><th>Oluşturulma</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((account) => (
              <tr key={account.id}>
                <td>
                  <strong>{account.display_name}</strong>
                  <div className="row-subtitle">{account.email}{account.id === currentUserID ? " (siz)" : ""}</div>
                </td>
                <td>{account.roles.map((role) => roleLabels[role] ?? role).join(", ") || "—"}</td>
                <td>
                  <span className={`status ${account.status === "active" ? "cleared" : "blocked"}`}>
                    {account.status === "active" ? "Aktif" : "Devre dışı"}
                  </span>
                </td>
                <td>{new Date(account.created_at).toLocaleDateString("tr-TR")}</td>
                <td>
                  <button className="icon-button compact" type="button" title="Kullanıcıyı düzenle" onClick={() => { setSelected(account); editDialog.current?.showModal(); }}>
                    <KeyRound size={16} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && users.length === 0 && (
          <div className="empty-state"><p>Kullanıcı bulunamadı.</p></div>
        )}
      </div>

      <dialog ref={createDialog} className="source-dialog">
        <form onSubmit={createUser}>
          <div className="dialog-header">
            <div>
              <span>Kullanıcı yönetimi</span>
              <h2>Yeni kullanıcı</h2>
            </div>
            <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => createDialog.current?.close()}>
              <X size={19} aria-hidden="true" />
            </button>
          </div>
          <div className="form-grid">
            <label className="full-width">E-posta<input name="email" type="email" required maxLength={320} /></label>
            <label className="full-width">Görünen ad<input name="display_name" required maxLength={120} /></label>
            <label className="full-width">Parola (en az 12 karakter)<input name="password" type="password" required minLength={12} /></label>
            <fieldset className="full-width role-fieldset">
              <legend>Roller</legend>
              {Object.entries(roleLabels).map(([value, label]) => (
                <label key={value} className="role-option">
                  <input type="checkbox" name="roles" value={value} />
                  {label}
                </label>
              ))}
            </fieldset>
          </div>
          <div className="dialog-actions">
            <button className="text-button" type="button" onClick={() => createDialog.current?.close()}>İptal</button>
            <button className="primary-button" type="submit" disabled={saving}>Kullanıcıyı oluştur</button>
          </div>
        </form>
      </dialog>

      <dialog ref={editDialog} className="source-dialog" key={selected?.id ?? "none"}>
        {selected && (
          <form onSubmit={updateUser}>
            <div className="dialog-header">
              <div>
                <span>{selected.email}</span>
                <h2>Kullanıcıyı düzenle</h2>
              </div>
              <button className="icon-button" type="button" title="Pencereyi kapat" onClick={() => { editDialog.current?.close(); setSelected(null); }}>
                <X size={19} aria-hidden="true" />
              </button>
            </div>
            <div className="form-grid">
              <label className="full-width">Görünen ad<input name="display_name" defaultValue={selected.display_name} required maxLength={120} /></label>
              <label>
                Durum
                <select name="status" defaultValue={selected.status} disabled={selected.id === currentUserID}>
                  <option value="active">Aktif</option>
                  <option value="disabled">Devre dışı</option>
                </select>
              </label>
              <label>Yeni parola (opsiyonel)<input name="new_password" type="password" minLength={12} placeholder="Değiştirmek için doldurun" /></label>
              <fieldset className="full-width role-fieldset">
                <legend>Roller</legend>
                {Object.entries(roleLabels).map(([value, label]) => (
                  <label key={value} className="role-option">
                    <input type="checkbox" name="roles" value={value} defaultChecked={selected.roles.includes(value)} />
                    {label}
                  </label>
                ))}
              </fieldset>
              {selected.id === currentUserID && (
                <p className="muted-copy full-width">Kendi hesabınızın durumunu değiştiremez veya admin rolünüzü kaldıramazsınız.</p>
              )}
            </div>
            <div className="dialog-actions">
              <button className="text-button" type="button" onClick={() => { editDialog.current?.close(); setSelected(null); }}>İptal</button>
              <button className="primary-button" type="submit" disabled={saving}>Kaydet</button>
            </div>
          </form>
        )}
      </dialog>
    </section>
  );
}
