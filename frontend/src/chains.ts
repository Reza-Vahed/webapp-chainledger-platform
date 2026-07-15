// Muss synchron zur Backend-Registry bleiben (siehe src/api_client/chains.py) -
// gleiches manuelle Sync-Pattern wie types.ts fuer api/schemas.py (kein
// OpenAPI-Codegen im MVP).
export const SUPPORTED_CHAINS = ["ethereum", "arbitrum"] as const;
export type ChainKey = (typeof SUPPORTED_CHAINS)[number];
export const DEFAULT_CHAIN: ChainKey = "ethereum";
