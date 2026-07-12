// Sürüm ve build kimliği. Değerler build sırasında next.config.ts tarafından
// enjekte edilir (package.json sürümü + git kısa SHA). Değişkenler yoksa
// geliştirme varsayılanına düşülür.

export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0";
export const APP_BUILD = process.env.NEXT_PUBLIC_APP_BUILD ?? "dev";

/** "Derlem · v0.1.0 · build 424b454" biçiminde tek satırlık damga. */
export const versionLabel = `Derlem · v${APP_VERSION} · build ${APP_BUILD}`;
