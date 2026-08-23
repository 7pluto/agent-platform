"""Provider-aware validation gate for publishing an Agent configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.control_plane.assembly import ResolvedAssemblyResource, resolve_agent_assembly
from app.core.errors import ApiError
from app.db.models import KnowledgeIndexVersionRow, ResourceDescriptorRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.resources.discovery import get_resource_discovery_service
from app.resources.providers.registry import provider_registry
from app.resources.registry_models import (
    DiscoveryDriftStatus,
    ResourceType,
    ResourceValidationType,
)
from app.resources.validation import get_resource_validation_service
from app.secrets.vault import get_secret_vault


@dataclass
class AgentValidationOutcome:
    bindings: list[ResolvedAssemblyResource] = field(default_factory=list)
    blocking_errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.blocking_errors


class AgentValidationService:
    async def require_valid(self, specification: dict[str, Any], principal: Principal) -> AgentValidationOutcome:
        outcome = await self.validate(specification, principal)
        if not outcome.valid:
            raise ApiError(
                409,
                "AGENT_VALIDATION_FAILED",
                "Agent 配置未通过发布校验",
                {"blocking_errors": outcome.blocking_errors, "warnings": outcome.warnings},
            )
        return outcome

    async def validate(self, specification: dict[str, Any], principal: Principal) -> AgentValidationOutcome:
        outcome = AgentValidationOutcome()
        try:
            outcome.bindings = await resolve_agent_assembly(specification, principal)
        except ApiError as exc:
            outcome.blocking_errors.append({"code": exc.code, "message": exc.message})
            return outcome

        await self._check_lifecycle(outcome, principal)
        for binding in outcome.bindings:
            resource = binding.resource
            await self._check_secrets(resource.config, principal, outcome)
            if resource.resource_type == ResourceType.TOOL and resource.config.get("kind") == "DIFY_FLOW":
                await self._check_dify(resource, principal, outcome)
            elif resource.resource_type == ResourceType.TOOL and resource.config.get("kind") == "HTTP":
                await self._require_test(resource.resource_version_id, "HTTP_TOOL_TEST_REQUIRED", "HTTP Tool 必须先通过测试", principal, outcome)
            elif resource.resource_type == ResourceType.MCP_CONNECTION:
                await self._check_mcp(resource, principal, outcome)
            elif resource.resource_type == ResourceType.KNOWLEDGE:
                await self._check_knowledge(resource, principal, outcome)
        return outcome

    async def _check_lifecycle(self, outcome: AgentValidationOutcome, principal: Principal) -> None:
        if get_settings().storage_mode != "postgres" or not outcome.bindings:
            return
        resource_ids = [item.resource.resource_id for item in outcome.bindings]
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = (await session.scalars(select(ResourceDescriptorRow).where(
                    ResourceDescriptorRow.tenant_id == principal.tenant_id,
                    ResourceDescriptorRow.resource_id.in_(resource_ids),
                ))).all()
        archived = {row.resource_id for row in rows if row.lifecycle_status == "ARCHIVED"}
        for binding in outcome.bindings:
            if binding.resource.resource_id in archived:
                self._block(outcome, "RESOURCE_ARCHIVED", f"资源 {binding.resource.resource_version_id} 已归档")

    async def _check_secrets(
        self, config: dict[str, Any], principal: Principal, outcome: AgentValidationOutcome,
    ) -> None:
        refs = self._secret_refs(config)
        for secret_ref in refs:
            try:
                await get_secret_vault().resolve(secret_ref, principal.tenant_id, principal.external_user_id)
            except ApiError as exc:
                self._block(outcome, exc.code, exc.message)

    async def _check_dify(self, resource, principal: Principal, outcome: AgentValidationOutcome) -> None:
        if not await get_resource_validation_service().has_successful_validation(
            resource.resource_version_id, principal, ResourceValidationType.VALIDATE,
        ):
            self._block(outcome, "DIFY_VALIDATION_REQUIRED", "Dify 应用必须先通过连接与调用验证")
            return
        result = await provider_registry.resolve(resource.resource_type, resource.config, principal).probe(resource.config)
        if not result.ok:
            self._block(outcome, str(result.error_code or "DIFY_UNAVAILABLE"), result.message or "Dify 应用当前不可用")

    async def _check_mcp(self, resource, principal: Principal, outcome: AgentValidationOutcome) -> None:
        result = await provider_registry.resolve(resource.resource_type, resource.config, principal).probe(resource.config)
        if not result.ok:
            self._block(outcome, str(result.error_code or "MCP_UNAVAILABLE"), result.message or "MCP Connection 当前不可用")

    async def _check_knowledge(self, resource, principal: Principal, outcome: AgentValidationOutcome) -> None:
        provider = str(resource.config.get("provider", "LOCAL")).upper()
        if provider == "LOCAL":
            if get_settings().storage_mode != "postgres":
                outcome.warnings.append({"code": "KNOWLEDGE_INDEX_NOT_VERIFIED", "message": "内存模式无法验证本地知识库活跃索引"})
                return
            async with get_session_factory()() as session:
                async with session.begin():
                    await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                    active = await session.scalar(select(KnowledgeIndexVersionRow.index_version_id).where(
                        KnowledgeIndexVersionRow.tenant_id == principal.tenant_id,
                        KnowledgeIndexVersionRow.knowledge_resource_version_id == resource.resource_version_id,
                        KnowledgeIndexVersionRow.status == "ACTIVE",
                    ))
            if active is None:
                self._block(outcome, "KNOWLEDGE_INDEX_NOT_ACTIVE", "本地知识库没有活跃索引")
            return
        if provider == "RAGFLOW":
            report = await get_resource_discovery_service().check_drift(resource, principal, create_draft=False)
            if report.status in {DiscoveryDriftStatus.MISSING, DiscoveryDriftStatus.UNAVAILABLE}:
                self._block(outcome, f"RAGFLOW_{report.status.value}", report.message or "RAGFlow Dataset 当前不可用")
            elif report.status == DiscoveryDriftStatus.CHANGED:
                outcome.warnings.append({"code": "RAGFLOW_DATASET_CHANGED", "message": "RAGFlow Dataset 元数据已变化，建议先审核新版本"})
            await self._require_test(resource.resource_version_id, "RAGFLOW_TEST_REQUIRED", "RAGFlow Knowledge 必须先通过检索测试", principal, outcome)
            return
        if provider == "REMOTE_HTTP":
            await self._require_test(resource.resource_version_id, "REMOTE_KNOWLEDGE_TEST_REQUIRED", "外部 HTTP Knowledge 必须先通过检索测试", principal, outcome)
            return
        self._block(outcome, "KNOWLEDGE_PROVIDER_UNSUPPORTED", f"不支持的 Knowledge Provider：{provider}")

    async def _require_test(
        self, version_id, code: str, message: str, principal: Principal, outcome: AgentValidationOutcome,
    ) -> None:
        if not await get_resource_validation_service().has_successful_validation(
            version_id, principal, ResourceValidationType.TEST,
        ):
            self._block(outcome, code, message)

    @staticmethod
    def _secret_refs(value: Any) -> set[str]:
        refs: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() == "secret_ref" and isinstance(item, str) and item.startswith("vault://"):
                    refs.add(item)
                else:
                    refs.update(AgentValidationService._secret_refs(item))
        elif isinstance(value, list):
            for item in value:
                refs.update(AgentValidationService._secret_refs(item))
        return refs

    @staticmethod
    def _block(outcome: AgentValidationOutcome, code: str, message: str) -> None:
        issue = {"code": code, "message": message}
        if issue not in outcome.blocking_errors:
            outcome.blocking_errors.append(issue)


_service = AgentValidationService()


def get_agent_validation_service() -> AgentValidationService:
    return _service
