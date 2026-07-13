import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../i18n";

const NATIVE_LABELS: Record<SupportedLanguage, string> = {
  de: "Deutsch",
  en: "English",
  fa: "فارسی",
};

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLanguage;

  return (
    <select
      className="language-switcher"
      value={current}
      onChange={(event) => void i18n.changeLanguage(event.target.value)}
      aria-label={t("language.label")}
      title={t("language.label")}
    >
      {SUPPORTED_LANGUAGES.map((lang) => (
        <option key={lang} value={lang}>
          {NATIVE_LABELS[lang]}
        </option>
      ))}
    </select>
  );
}
