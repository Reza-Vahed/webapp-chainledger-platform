import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DEFAULT_CHAIN, type ChainKey } from "../chains";
import { ChainSelect } from "./ChainSelect";

// Gleiches Muster wie ADDRESS_PATTERN im Backend (src/cli.py) - clientseitig
// nur fuer schnelles Feedback, das Backend validiert ohnehin nochmal. Das
// 0x+40-Hex-Format ist chain-uebergreifend identisch (EVM-Adressformat).
const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

interface AddressFormProps {
  onSubmit: (address: string, chain: ChainKey) => void;
  disabled: boolean;
}

export function AddressForm({ onSubmit, disabled }: AddressFormProps) {
  const { t } = useTranslation();
  const [address, setAddress] = useState("");
  const [chain, setChain] = useState<ChainKey>(DEFAULT_CHAIN);
  const [hasValidationError, setHasValidationError] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = address.trim();
    if (!ADDRESS_PATTERN.test(trimmed)) {
      setHasValidationError(true);
      return;
    }
    setHasValidationError(false);
    onSubmit(trimmed, chain);
  }

  return (
    <form onSubmit={handleSubmit} className="address-form">
      <label htmlFor="wallet-address">{t("addressForm.label")}</label>
      <div className="address-form__row">
        <input
          id="wallet-address"
          type="text"
          placeholder={t("addressForm.placeholder")}
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
        />
        <ChainSelect value={chain} onChange={setChain} disabled={disabled} />
        <button type="submit" disabled={disabled || address.trim().length === 0}>
          {disabled ? t("addressForm.submitting") : t("addressForm.submit")}
        </button>
      </div>
      {hasValidationError && (
        <p className="form-error" role="alert">
          {t("addressForm.validationError")}
        </p>
      )}
    </form>
  );
}
