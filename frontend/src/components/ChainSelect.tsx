import { useTranslation } from "react-i18next";
import { SUPPORTED_CHAINS, type ChainKey } from "../chains";

interface ChainSelectProps {
  value: ChainKey;
  onChange: (chain: ChainKey) => void;
  disabled: boolean;
}

export function ChainSelect({ value, onChange, disabled }: ChainSelectProps) {
  const { t } = useTranslation();

  return (
    <label className="chain-select">
      {t("chainSelect.label")}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as ChainKey)}
        disabled={disabled}
      >
        {SUPPORTED_CHAINS.map((chain) => (
          <option key={chain} value={chain}>
            {t(`chain.${chain}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
