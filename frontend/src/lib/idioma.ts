export type Idioma = "pt" | "en";

/** Texto nos dois idiomas, escolhido na renderização. */
export function tr(lang: Idioma, pt: string, en: string): string {
  return lang === "pt" ? pt : en;
}
