# Secret management policy

## Locked V1 policy

Every newly registered business or provider credential uses the tenant Secret Vault. This includes Model, Embedding, Dify Flow, authenticated MCP and future Tool/provider keys.

The UI submits the credential exactly once to an atomic registration endpoint. The API first tests the target connection, encrypts the credential with the platform master encryption key, and persists only a `vault://UUID` reference in resource definitions, immutable versions and execution manifests. API responses and audit records expose only the reference and a SHA-256 fingerprint; they never return the credential.

The platform master encryption key and infrastructure bootstrap passwords remain deployment-owned values in the restricted server `.env`. They are not business credentials and cannot be created from the tenant UI.

`env://VARIABLE` is a read-only compatibility mechanism for replaying legacy published resources. API persistence boundaries reject it for every new definition or version with `VAULT_SECRET_REF_REQUIRED`. New provider onboarding must use a Vault-backed atomic API.

## Adding another keyed integration

1. Add a dedicated request model whose credential field is write-only and is never used as a response model.
2. Test the remote connection without logging the request body or authorization header.
3. Store the credential through `SecretVault.create` and discard the plaintext value.
4. Persist only the returned `vault://UUID` and non-secret connection metadata.
5. Resolve the reference only inside the tenant-scoped worker transaction immediately before the outbound call.
6. Ensure manifests and audit events contain only the reference/fingerprint, then add tests for plaintext rejection, tenant isolation and response redaction.
