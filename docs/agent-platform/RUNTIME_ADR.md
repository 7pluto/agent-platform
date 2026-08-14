# Runtime Adapter ADR

- Status: accepted for Stage 1
- Decision: keep the platform runtime behind `RuntimeAdapter` and bind every Run to an `ExecutionManifest` before execution.
- Development implementations: `MockRuntimeAdapter` and `LangGraphBaselineAdapter`; both are deterministic and cancellation-aware, while only the latter wraps an official LangGraph StateGraph.
- Production selection: deferred until the serial LangGraph -> DeerFlow -> DeepAgents PoC sequence passes the hard gates in `IMPLEMENTATION_PLAN.md`.

The control API is not allowed to import harness-private state or return harness-specific schemas. Runtime events are translated into platform event names at the adapter boundary.