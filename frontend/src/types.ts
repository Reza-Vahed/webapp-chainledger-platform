// Spiegelt api/schemas.py (Backend) - bewusst manuell synchron gehalten,
// da das MVP keine OpenAPI-Codegen-Pipeline hat.

export type JobState = "queued" | "running" | "done" | "error";
export type CategoryStatus = "pending" | "in_progress" | "done" | "error";

export interface CategoryProgress {
  category: string;
  status: CategoryStatus;
  pages_fetched: number;
  records_fetched: number;
  error: string | null;
}

export interface AddressProgress {
  address: string;
  categories: Record<string, CategoryProgress>;
}

export interface JobStatusResponse {
  job_id: string;
  state: JobState;
  stage: string | null;
  addresses: Record<string, AddressProgress>;
  total_transactions: number | null;
  unclassified_count: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  csv_available: boolean;
  json_available: boolean;
}

export interface ImportCreatedResponse {
  job_id: string;
}

export interface TransactionOut {
  wallet_address: string;
  tx_hash: string;
  timestamp: string;
  category: string;
  direction: string;
  amount: string;
  token_symbol: string;
  token_contract_address: string | null;
  from_address: string;
  to_address: string | null;
  gas_fee_eth: string | null;
  confidence: number;
  warnings: string[];
  source: string;
  record_type: string;
  block_number: number;
  is_error: boolean;
}

export interface TransactionsPage {
  items: TransactionOut[];
  total: number;
  page: number;
  page_size: number;
}
