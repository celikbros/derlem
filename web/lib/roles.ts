// Rol tanımlarının tek kaynağı. Hem giriş ekranındaki yardım penceresi hem de
// uygulama içindeki Rehber (guide-panel) buradan okur; böylece iki yerdeki
// açıklamalar birbirinden ayrışmaz.

export type RoleStart = {
  /** İlk adımların geçtiği ekran; hoş geldin kartındaki düğme buraya götürür. */
  view: "sources" | "review" | "releases" | "users" | "contribute" | "guide";
  /** Düğme metni: "İncelemeye başla". */
  label: string;
};

export type RoleInfo = {
  /** Kanonik API rolü (user.roles içindeki değer). */
  role: string;
  /** Giriş kartındaki kısa etiket (admin, manager, ...). */
  label: string;
  /** Başlık: "Yönetici (admin)". */
  title: string;
  /** Tek satırlık özet — yalnız giriş ekranındaki hesap kartı kullanır.
   *  (Hoş geldin ipucu `title` + `who` alanlarını gösterir, `summary`'yi değil.) */
  summary: string;
  /** "Kimdir?" — tek cümlelik kişi tarifi. */
  who: string;
  /** "Ne iş yapar?" — ayrıntılı görev listesi. */
  duties: string[];
  /** "Bugün ne yapacağım?" — ilk oturum için sıralı somut adımlar;
   *  hoş geldin kartı ve Rehber'deki yol haritası buradan okur. */
  firstSteps: string[];
  /** İlk adımların başladığı ekran ve çağrı düğmesi. */
  start: RoleStart;
};

export const ROLE_INFO: RoleInfo[] = [
  {
    role: "admin",
    label: "admin",
    title: "Yönetici (admin)",
    summary: "Yönetim: kullanıcılar, release freeze — tüm yetkiler",
    who: "Sistemin sahibi ve işleticisi.",
    duties: [
      "Tüm ekranları görür ve tüm işlemleri yapabilir.",
      "Yalnızca bu role açık iki kritik yetki: release freeze ve kontrollü yeniden örnekleme.",
      "Kullanıcı hesaplarını ve rolleri yönetir.",
    ],
    firstSteps: [
      "Kullanıcılar ekranından ekip hesaplarını açın: e-posta, görünen ad, en az 12 karakterlik geçici parola ve rol.",
      "Ekibe adresi ve giriş bilgilerini iletin; herkes ilk girişte rolüne göre yönlendirilir.",
      "Akışı Kaynaklar ve İşler ekranından izleyin; release freeze ve yeniden örnekleme yalnız sizdedir.",
    ],
    start: { view: "users", label: "Kullanıcıları aç" },
  },
  {
    role: "data_manager",
    label: "manager",
    title: "Veri yöneticisi (data_manager)",
    summary: "Kaynak kaydı açma ve dosya yükleme",
    who: "Veriyi sisteme sokan kişi.",
    duties: [
      "Yeni kaynak kaydı açar, metadata ve hak bilgisini düzenler.",
      "Dosya yükler veya yerel ingest başlatır.",
      "Release taslağı oluşturur; manifest ve export indirir. Freeze edemez.",
    ],
    firstSteps: [
      "Kaynaklar ekranında “Yeni kaynak” ile künyeyi açın: ad, içerik amacı, lisans, hak durumu ve alan (domain) etiketi.",
      "Kaynak satırına tıklayıp sağ panelden dosyanızı yükleyin: UTF-8 .txt (satır başına bir belge), JSONL, PDF veya DOCX.",
      "Gerisini program yapar: PII taraması, tekrar kontrolü, 200 örnek. İlerlemeyi İşler ekranından izleyin.",
      "Örneklem hazır olunca incelemeyi inceleyiciler yapar; kendi yüklediğiniz kaynağı siz onaylayamazsınız.",
    ],
    start: { view: "sources", label: "Kaynaklara git" },
  },
  {
    role: "editor",
    label: "editor",
    title: "Editör (editor)",
    summary: "Metadata ve belge içeriği düzeltme",
    who: "Metni ve künyeyi düzelten kişi.",
    duties: [
      "Kaynak metadata’sını düzenler.",
      "Belge içeriğini düzeltip yeni immutable sürüm oluşturur.",
      "Kaynak açamaz, onay kararı veremez.",
    ],
    firstSteps: [
      "Kaynaklar ekranında satıra tıklayın; künye ve hak bilgisini sağ panelden düzeltin.",
      "Örnek belgelerdeki metin hatalarını düzeltin; her düzeltme yeni değişmez sürüm oluşturur.",
      "Onay kararı sizde değildir; düzelttiğiniz belgeyi inceleyici yeniden değerlendirir.",
    ],
    start: { view: "sources", label: "Kaynaklara git" },
  },
  {
    role: "moderator",
    label: "moderator",
    title: "Moderatör (moderator)",
    summary: "Örnek inceleme ve kaynak onayı",
    who: "Kaynağı onaylayan inceleyici.",
    duties: [
      "İncelemede “Güvenli paket al” ile kendi belge paketini alır; örnekleri okuyup kalite puanı verir.",
      "Kaynak için onay, ret veya hassas inceleme kararı verir.",
      "Kendi yüklediği kaynağı onaylayamaz (self-review engeli).",
    ],
    firstSteps: [
      "İnceleme ekranında kuyruktaki kaynağa tıklayın.",
      "“Güvenli paket al” düğmesiyle 10-20 belgelik iş paketinizi alın; belgeler 15 dakika yalnız size atanır.",
      "Paketinizdeki her belgeyi okuyun, kalite puanı verin, onaylayın veya reddedin; toplu karar da verebilirsiniz.",
      "Ara verecekseniz “Paketi bırak” deyin. Tüm örnekler bitince kaynak kararı (onay/ret) verilir.",
    ],
    start: { view: "review", label: "İncelemeye başla" },
  },
  {
    role: "expert_reviewer",
    label: "expert",
    title: "Uzman inceleyici (expert_reviewer)",
    summary: "Hassas inceleme ve benzerlik etiketleme",
    who: "Hassas kararları ve benzerlik etiketlemesini yapan uzman.",
    duties: [
      "Moderatör ile aynı inceleme ve karar yetkilerine sahiptir.",
      "Benzerlik ekranında yakın-tekrar çiftlerini körlemeli olarak etiketler.",
    ],
    firstSteps: [
      "İnceleme ekranında kuyruktaki kaynağa tıklayıp “Güvenli paket al” ile iş paketinizi alın.",
      "Paketinizdeki belgeleri okuyun, kalite puanı verin, onaylayın veya reddedin.",
      "Benzerlik ekranında yakın-tekrar çiftlerini körlemeli etiketleyin; diğer inceleyicilerin kararını görmezsiniz.",
    ],
    start: { view: "review", label: "İncelemeye başla" },
  },
  {
    role: "contributor",
    label: "contributor",
    title: "Katkıcı (contributor)",
    summary: "Soru-cevap çifti ve serbest metin katkısı",
    who: "Kendi ürettiği metinle veri havuzunu besleyen kişi.",
    duties: [
      "Katkılar ekranından soru-cevap çifti veya serbest metin gönderir.",
      "Gönderdiği katkıların durumunu izler; demetlenmemiş katkısını geri çekebilir.",
      "Katkılar doğrudan corpus'a girmez: havuz kaynağa demetlenir ve PII, tekrar ve insan inceleme kapılarından geçer.",
    ],
    firstSteps: [
      "Katkılar ekranını açın ve görev tipini seçin: soru-cevap çifti veya serbest metin.",
      "Metninizi yazın, alan (domain) etiketini ekleyin ve kullanım şartını onaylayıp gönderin.",
      "Gönderdikleriniz listenizde birikir; demetlenmeden önce hatalı katkıyı geri çekebilirsiniz.",
      "Katkılarınız kaynağa demetlenince normal kalite kapılarından geçer; sonucu durum sütunundan izlersiniz.",
    ],
    start: { view: "contribute", label: "Katkı vermeye başla" },
  },
  {
    role: "consumer_team",
    label: "consumer",
    title: "Tüketici ekip (consumer_team)",
    summary: "Frozen release görüntüleme ve indirme",
    who: "Çıktıyı kullanan model/eğitim ekibi.",
    duties: [
      "Yalnızca donmuş (frozen) release’leri görür.",
      "Manifest, kaynak artifact’i ve JSONL/TXT export indirir; checksum ile doğrular.",
    ],
    firstSteps: [
      "Sürümler ekranında donmuş (frozen) release'i açın.",
      "Manifest ve JSONL/TXT export'u indirin; SHA256 sağlamasını doğrulayın.",
    ],
    start: { view: "releases", label: "Sürümlere git" },
  },
];

/** Kanonik role göre arama (guide-panel için). */
export const roleInfoByRole: Record<string, RoleInfo> = Object.fromEntries(
  ROLE_INFO.map((info) => [info.role, info]),
);

/** Giriş etiketine göre kısa özet (giriş kartı ve hoş geldin ipucu için). */
export const roleSummaryByLabel: Record<string, string> = Object.fromEntries(
  ROLE_INFO.map((info) => [info.label, info.summary]),
);
