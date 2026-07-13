import { useState, type FormEvent } from "react";

// Gleiches Muster wie ADDRESS_PATTERN im Backend (src/cli.py) - clientseitig
// nur fuer schnelles Feedback, das Backend validiert ohnehin nochmal.
const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

interface AddressFormProps {
  onSubmit: (address: string) => void;
  disabled: boolean;
}

export function AddressForm({ onSubmit, disabled }: AddressFormProps) {
  const [address, setAddress] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = address.trim();
    if (!ADDRESS_PATTERN.test(trimmed)) {
      setValidationError("Bitte eine gültige Ethereum-Adresse eingeben (0x + 40 Hex-Zeichen).");
      return;
    }
    setValidationError(null);
    onSubmit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className="address-form">
      <label htmlFor="wallet-address">Ethereum-Wallet-Adresse</label>
      <div className="address-form__row">
        <input
          id="wallet-address"
          type="text"
          placeholder="0x..."
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
        />
        <button type="submit" disabled={disabled || address.trim().length === 0}>
          {disabled ? "Läuft…" : "Import starten"}
        </button>
      </div>
      {validationError && (
        <p className="form-error" role="alert">
          {validationError}
        </p>
      )}
    </form>
  );
}
