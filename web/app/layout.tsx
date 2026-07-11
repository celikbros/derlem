import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Derlem",
  description: "Veri atölyesi yönetim arayüzü",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: tarayıcı eklentileri (Trancy, Grammarly vb.)
    // React yüklenmeden html/body özniteliklerini değiştirebiliyor; yalnız bu
    // iki elemanın öznitelik farkları yok sayılır, içerik denetimi sürer.
    <html lang="tr" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
