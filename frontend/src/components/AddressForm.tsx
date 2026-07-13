import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

// Gleiches Muster wie ADDRESS_PATTERN im Backend (src/cli.py) - clientseitig
// nur fuer schnelles Feedback, das Backend validiert ohnehin nochmal.
const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

interface AddressFormProps {
  onSubmit: (address: string) => void;
  disabled: boolean;
}

export function AddressForm({ onSubmit, disabled }: AddressFormProps) {
  const { t } = useTranslation();
  const [address, setAddress] = useState("");
  const [hasValidationError, setHasValidationError] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = address.trim();
    if (!ADDRESS_PATTERN.test(trimmed)) {
      setHasValidationError(true);
      return;
    }
    setHasValidationError(false);
    onSubmit(trimmed);
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
