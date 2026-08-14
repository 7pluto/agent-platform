# Open Source Reuse Decision

## Current status

Stage 1 starts with a dependency-free runtime contract and deterministic mock harness. The API and persistence layers only depend on `RuntimeAdapter`; they do not expose any harness-private schema.

| Candidate | Status | Reason |
|---|---|---|
| LangGraph official APIs | `WRAP` | `LangGraphBaselineAdapter` now validates the Adapter boundary, platform events, cancellation checks and Manifest injection without binding the control API to LangGraph state. PostgreSQL checkpoint/recovery remains the next gate. |
| DeerFlow | `NOT_USED` | PoC is not executed in the current repository; it may only be selected after the LangGraph baseline and hard-gate checks. |
| DeepAgents | `NOT_USED` | Only evaluated if the DeerFlow PoC fails its hard gates. |
| `langchain-mcp-adapters` | `NOT_USED` | MCP is intentionally kept outside the first runtime slice. |
| Current `MockRuntimeAdapter` | `REFERENCE_ONLY` | Internal deterministic harness for contract and lifecycle tests; it is not an external dependency and never a production model runtime. |

## Hard gates before selecting a harness

A candidate must support manifest-driven model/prompt/tool injection, PostgreSQL checkpointing, thread recovery, streaming, cooperative cancellation, tenant-safe state, and an acceptable license/version pin. The platform must be able to upgrade the candidate without changing the public Run API.

## Next PoC output

The LangGraph baseline event/cancellation adapter test is complete. The next gate is PostgreSQL checkpoint/recovery under a separate Worker process, followed by the serial DeerFlow PoC. DeerFlow is not evaluated in parallel.