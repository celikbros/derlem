"use client";

import { BookOpen, ClipboardCheck, Database, GitCompareArrows, Library, ListTodo, PackageCheck, Rocket, ShieldCheck } from "lucide-react";

import { roleInfoByRole } from "@/lib/roles";
import type { User } from "@/lib/types";

export function GuidePanel({ user }: { user: User }) {
  const userRoles = user.roles.filter((role) => roleInfoByRole[role]);
  return (
    <section className="guide-layout" aria-label="Derlem kullanım rehberi">
      <div className="guide-card guide-intro">
        <h3><BookOpen size={17} aria-hidden="true" /> Derlem nedir, neden var?</h3>
        <p>
          Bir dil modeli ancak verisi kadar iyidir — ve internetten toplanmış veri çoğu zaman
          hakları belirsiz, tekrarlı ve kirlidir. Derlem bu sorunu çözer: LLM ve tokenizer
          eğitiminde kullanılacak metin verisini <strong>hakları belli</strong>,{" "}
          <strong>kalitesi insan onaylı</strong> ve <strong>tekrarı ayıklanmış</strong> hale
          getiren bir veri atölyesidir. Kimse buraya elle metin yazmaz: var olan corpus
          dosyaları sisteme alınır, otomatik kalite kapılarından geçirilir, insan incelemesiyle
          onaylanır ve eğitim ekiplerine değişmez (frozen) paketler olarak sunulur.
        </p>
        <p>
          Çıktılar modelden ve tokenizer’dan bağımsızdır; aynı paketi herhangi bir model ekibi
          kullanabilir. Sizin bu zincirde verdiğiniz her karar (puan, onay, ret, etiket) audit
          kaydına yazılır ve üretilen veri bankasının güven temelini oluşturur.
        </p>
      </div>

      {userRoles.length > 0 && (
        <div className="guide-card">
          <h3><Rocket size={17} aria-hidden="true" /> İlk günün yol haritası</h3>
          {userRoles.map((role) => (
            <div className="guide-role" key={role}>
              <strong>{roleInfoByRole[role].title}</strong>
              <ol className="guide-steps">
                {roleInfoByRole[role].firstSteps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </div>
          ))}
        </div>
      )}

      <div className="guide-card">
        <h3>Veri yolculuğu: altı adım</h3>
        <ol className="guide-steps">
          <li>
            <strong>Kaynak kaydı.</strong> Veri yöneticisi Kaynaklar ekranında “Yeni kaynak” ile
            künyeyi girer: ad, içerik amacı, lisans, hak durumu ve köken. İçerik amacı
            (pretrain, eval, ...) kayıttan sonra değiştirilemez.
          </li>
          <li>
            <strong>Dosya alımı.</strong> Kaynak detayından dosya yüklenir. Dosya SHA256
            kimliğiyle değişmez depoya kopyalanır; artık kimse içeriğini değiştiremez.
          </li>
          <li>
            <strong>Otomatik kapılar.</strong> Arka plandaki worker PII taraması, tekrar
            kontrolü ve 200 belgelik risk puanlı örneklem çıkarır. İlerleme İşler ekranında
            görünür; sonuçlar kaynak detayına işlenir.
          </li>
          <li>
            <strong>İnsan incelemesi.</strong> İnceleyici, İnceleme ekranındaki kuyruktan
            kaynağı açar ve “Güvenli paket al” ile kendi belge paketini alır; aynı belge
            asla iki kişiye dağıtılmaz. Örnekleri okuyup kalite puanı verir, hak/lisans
            kanıtını doğrular. Tüm kapılar temizse kaynağı onaylar.
          </li>
          <li>
            <strong>Release ve freeze.</strong> Aynı amaçtaki onaylı kaynaklardan Sürümler
            ekranında taslak release oluşturulur. Yönetici freeze ettiğinde kapılar yeniden
            koşulur, eval/holdout sızıntı kontrolü yapılır ve SHA256 manifest’i sabitlenir.
          </li>
          <li>
            <strong>Tüketim.</strong> Model ekibi frozen release’in manifestini ve
            JSONL/TXT export’unu indirir, checksum ile doğrular ve kendi eğitim hattında
            kullanır. Düzeltme gerekirse mevcut release değişmez; yeni release çıkarılır.
          </li>
        </ol>
      </div>

      <div className="guide-card">
        <h3>Ekranlar</h3>
        <ul className="guide-screens">
          <li><Library size={16} aria-hidden="true" /> <strong>Kaynaklar:</strong> tüm veri kaynaklarının kataloğu; her satırda sıradaki kapı gösterilir.</li>
          <li><ClipboardCheck size={16} aria-hidden="true" /> <strong>İnceleme:</strong> karar bekleyen kaynakların öncelik sıralı kuyruğu ve örnek belge incelemesi.</li>
          <li><GitCompareArrows size={16} aria-hidden="true" /> <strong>Benzerlik:</strong> yakın-tekrar aday çiftlerinin körlemeli insan etiketlemesi.</li>
          <li><PackageCheck size={16} aria-hidden="true" /> <strong>Sürümler:</strong> taslak ve frozen release’ler, kapı sonuçları, manifest ve export indirme.</li>
          <li><ListTodo size={16} aria-hidden="true" /> <strong>İşler:</strong> arka plan işlerinin durumu ve canlı ilerlemesi.</li>
        </ul>
      </div>

      {userRoles.length > 0 && (
        <div className="guide-card">
          <h3><ShieldCheck size={17} aria-hidden="true" /> Sizin yetkileriniz</h3>
          {userRoles.map((role) => (
            <div className="guide-role" key={role}>
              <strong>{roleInfoByRole[role].title}</strong>
              <p className="guide-role-who">{roleInfoByRole[role].who}</p>
              <ul>
                {roleInfoByRole[role].duties.map((line) => <li key={line}>{line}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="guide-card">
        <h3><Database size={17} aria-hidden="true" /> Küçük sözlük</h3>
        <dl className="guide-terms">
          <dt>Değişmez depo (immutable store)</dt>
          <dd>Dosyaların SHA256 kimliğiyle saklandığı, yazıldıktan sonra değiştirilemeyen alan.</dd>
          <dt>İçerik amacı (content purpose)</dt>
          <dd>Kaynağın hangi eğitim havuzuna ait olduğu (pretrain, eval, ...). Kayıtta sabitlenir; eval verisinin eğitime sızmasını önler.</dd>
          <dt>PII kapısı</dt>
          <dd>TCKN, IBAN, e-posta, telefon ve kart kalıplarının taranması. Bulgu varsa kaynak onaylanamaz; ham değer hiçbir yere yazılmaz.</dd>
          <dt>Tekrar (dedup) kapısı</dt>
          <dd>Aynı dosyanın veya aynı metnin farklı biçiminin ikinci kez onaylanmasını engeller.</dd>
          <dt>Örneklem</dt>
          <dd>Milyonlarca belgeden risk puanına göre seçilen, insan incelemesine sunulan 200 temsilci belge.</dd>
          <dt>Freeze / frozen release</dt>
          <dd>Release içeriğinin SHA256 manifest’iyle dondurulması. Frozen release asla değişmez; düzeltme yeni release olur.</dd>
        </dl>
      </div>
    </section>
  );
}
