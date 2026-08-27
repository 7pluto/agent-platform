from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin
from app.api.routes.mcp import (
    McpConnectionCreate,
    McpToolRegistration,
    RegisterDiscoveredToolsRequest,
    create_mcp_connection,
    discover_mcp_tools,
    register_discovered_tools_batch,
)
from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.bindings import get_external_binding_service
from app.resources.product_governance import ProductGovernance, PublicationSubject, apply_product_governance
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType, ResourceVersionRecord, ResourceVersionStatus
from app.governance.models import SubjectType


router = APIRouter(prefix="/admin/common-mcp", tags=["common-demo-mcp"])
registry = get_resource_registry()
bindings = get_external_binding_service()


class ToolSpec(BaseModel):
    external_name: str
    slug: str
    display_name: str
    summary: str
    when_to_use: str
    input_summary: str
    output_summary: str


class McpServerSpec(BaseModel):
    slug: str
    display_name: str
    endpoint: str
    description: str
    tools: list[ToolSpec]


class CommonMcpItem(BaseModel):
    kind: Literal["CONNECTION", "TOOL"]
    server: str
    name: str
    status: Literal["CREATED", "EXISTING", "FAILED"]
    resource_id: UUID | None = None
    resource_version_id: UUID | None = None
    message: str | None = None


class CommonMcpInstallResponse(BaseModel):
    pack_version: int = 1
    created_connections: int = 0
    existing_connections: int = 0
    created_tools: int = 0
    existing_tools: int = 0
    failed: int = 0
    items: list[CommonMcpItem] = Field(default_factory=list)


def _tool_governance(spec: ToolSpec, principal: Principal) -> McpToolRegistration:
    return McpToolRegistration(
        tool_name=spec.external_name,
        slug=spec.slug,
        display_name=spec.display_name,
        description=spec.summary,
        owner_user_id=principal.external_user_id,
        owner_dept_id=principal.dept_ids[0] if principal.dept_ids else None,
        one_line_summary=spec.summary,
        when_to_use=spec.when_to_use,
        when_not_to_use="不用于修改外部业务数据；演示 MCP 均为只读。",
        input_summary=spec.input_summary,
        output_summary=spec.output_summary,
        risk_level="LOW",
        read_only=True,
        tags=["MCP", "DEMO", "只读", "common-resource"],
        business_line="通用演示",
        audience="Agent 开发者与平台管理员",
        usage_scenarios="开发阶段验证 MCP 发现、Tool 纳管、权限和 Agent 调用链",
        publication_scope="SELECTED_SUBJECTS",
        publication_subjects=[
            PublicationSubject(subject_type=SubjectType.ROLE, subject_id="agent_developer"),
            PublicationSubject(subject_type=SubjectType.ROLE, subject_id="agent_admin"),
        ],
    )


def _connection_governance(spec: McpServerSpec, principal: Principal) -> ProductGovernance:
    return ProductGovernance(
        owner_user_id=principal.external_user_id,
        owner_dept_id=principal.dept_ids[0] if principal.dept_ids else None,
        one_line_summary=spec.description,
        when_to_use="平台需要发现或执行该演示 MCP Server 提供的 Tool 时使用。",
        when_not_to_use="Agent 不直接选择 Connection；应选择发现并纳管后的 Tool Resource。",
        input_summary="MCP Streamable HTTP 连接配置。",
        output_summary="可用于 tools/list 和 tools/call 的 MCP Connection。",
        risk_level="LOW",
        read_only=True,
        tags=["MCP", "DEMO", "connection", "common-resource"],
        business_line="通用演示",
        audience="Agent 开发者与平台管理员",
        usage_scenarios="MCP 能力发现、Playground 测试与 Tool 运行",
        publication_scope="SELECTED_SUBJECTS",
        publication_subjects=[
            PublicationSubject(subject_type=SubjectType.ROLE, subject_id="agent_developer"),
            PublicationSubject(subject_type=SubjectType.ROLE, subject_id="agent_admin"),
        ],
    )


SERVERS = [
    McpServerSpec(
        slug="common-demo-crm-mcp",
        display_name="演示 CRM MCP",
        endpoint="http://demo-crm-mcp:8090/mcp",
        description="提供只读客户资料与订单查询能力，用于演示 CRM 类 MCP 接入。",
        tools=[
            ToolSpec(external_name="query_customer", slug="common-mcp-query-customer", display_name="查询 CRM 客户", summary="按客户编号读取客户基本信息和客户等级。", when_to_use="需要核对客户基本资料或客户等级时。", input_summary="customer_id 客户编号。", output_summary="客户编号、名称、客户等级等基本信息。"),
            ToolSpec(external_name="list_customer_orders", slug="common-mcp-list-customer-orders", display_name="查询客户最近订单", summary="读取指定客户最近的订单列表。", when_to_use="需要了解客户最近订单和订单状态时。", input_summary="customer_id，以及可选 limit。", output_summary="订单编号、金额、状态等订单列表。"),
        ],
    ),
    McpServerSpec(
        slug="common-demo-ticket-mcp",
        display_name="演示工单 MCP",
        endpoint="http://demo-ticket-mcp:8092/mcp",
        description="提供只读工单查询与检索能力，用于演示客服和运维工单接入。",
        tools=[
            ToolSpec(external_name="query_ticket", slug="common-mcp-query-ticket", display_name="查询工单详情", summary="按工单编号读取状态、优先级、负责人和问题摘要。", when_to_use="用户给出明确工单编号并询问当前处理情况时。", input_summary="ticket_id 工单编号。", output_summary="工单状态、优先级、负责人、问题摘要和更新时间。"),
            ToolSpec(external_name="list_customer_tickets", slug="common-mcp-list-customer-tickets", display_name="查询客户最近工单", summary="读取指定客户最近的工单列表。", when_to_use="需要了解某个客户近期投诉或处理记录时。", input_summary="customer_id，以及可选 limit。", output_summary="该客户最近工单及当前状态。"),
            ToolSpec(external_name="search_tickets", slug="common-mcp-search-tickets", display_name="检索工单", summary="按关键词和可选状态检索工单。", when_to_use="没有明确工单编号，需要按问题关键词定位相关工单时。", input_summary="keyword，可选 status 和 limit。", output_summary="匹配关键词的工单列表。"),
        ],
    ),
    McpServerSpec(
        slug="common-demo-ops-mcp",
        display_name="演示运维 MCP",
        endpoint="http://demo-ops-mcp:8093/mcp",
        description="提供只读服务状态与故障事件查询，用于演示 IT 运维类 MCP。",
        tools=[
            ToolSpec(external_name="get_service_status", slug="common-mcp-service-status", display_name="查询服务状态", summary="读取服务当前健康状态、P95 延迟和错误率。", when_to_use="排查服务是否健康、当前是否存在明显性能异常时。", input_summary="service_name 服务名称。", output_summary="健康状态、P95 延迟、错误率和检查时间。"),
            ToolSpec(external_name="list_recent_incidents", slug="common-mcp-list-incidents", display_name="查询近期故障", summary="读取近期运维故障事件列表。", when_to_use="需要了解服务近期是否发生过故障或异常时。", input_summary="可选 service_name 和 limit。", output_summary="近期故障编号、级别、状态和摘要。"),
            ToolSpec(external_name="get_incident", slug="common-mcp-get-incident", display_name="查询故障详情", summary="按事件编号读取故障详情和处置状态。", when_to_use="已有明确 incident_id，需要查看故障详情时。", input_summary="incident_id 故障事件编号。", output_summary="故障服务、级别、状态、摘要和起止时间。"),
        ],
    ),
]


async def _published_connection(spec: McpServerSpec, principal: Principal) -> ResourceVersionRecord | None:
    definition = next((item for item in await registry.list_definitions(principal, ResourceType.MCP_CONNECTION) if item.slug == spec.slug), None)
    if definition is None:
        return None
    versions = await registry.list_versions(definition.resource_id, principal)
    published = [item for item in versions if item.status == ResourceVersionStatus.PUBLISHED]
    if not published:
        raise ApiError(409, "COMMON_MCP_CONFLICT", f"reserved MCP slug exists without a published version: {spec.slug}")
    return max(published, key=lambda item: item.version_number)


async def _ensure_connection(spec: McpServerSpec, principal: Principal) -> tuple[ResourceVersionRecord, str]:
    found = await _published_connection(spec, principal)
    if found:
        return found, "EXISTING"
    created = await create_mcp_connection(
        McpConnectionCreate(slug=spec.slug, display_name=spec.display_name, endpoint=spec.endpoint, timeout_seconds=5),
        principal,
    )
    await apply_product_governance(
        product=_connection_governance(spec, principal),
        resource_type=ResourceType.MCP_CONNECTION.value,
        resource_id=created.resource_id,
        resource_version_id=created.resource_version_id,
        source_type="MCP",
        source_ref=spec.endpoint,
        principal=principal,
    )
    return created, "CREATED"


async def _tool_state(connection: ResourceVersionRecord, tool: ToolSpec, principal: Principal) -> ResourceVersionRecord | None:
    connection_bindings = await bindings.list_for_connection(connection.resource_id, principal)
    binding = next((item for item in connection_bindings if item.external_type == "TOOL" and item.external_id == tool.external_name), None)
    if binding is None:
        return None
    versions = await registry.list_versions(binding.resource_id, principal)
    published = [item for item in versions if item.status == ResourceVersionStatus.PUBLISHED]
    return max(published, key=lambda item: item.version_number) if published else None


@router.post("/install", response_model=CommonMcpInstallResponse)
async def install_common_mcp(principal: Principal = Depends(require_platform_admin)) -> CommonMcpInstallResponse:
    response = CommonMcpInstallResponse()
    for server in SERVERS:
        try:
            connection, connection_status = await _ensure_connection(server, principal)
            response.items.append(CommonMcpItem(kind="CONNECTION", server=server.display_name, name=server.display_name, status=connection_status, resource_id=connection.resource_id, resource_version_id=connection.resource_version_id))
            if connection_status == "CREATED":
                response.created_connections += 1
            else:
                response.existing_connections += 1

            discovered = await discover_mcp_tools(connection.resource_version_id, principal)
            discovered_names = {item.name for item in discovered}
            missing = [tool.external_name for tool in server.tools if tool.external_name not in discovered_names]
            if missing:
                raise ApiError(409, "COMMON_MCP_TOOL_MISSING", f"MCP server did not advertise expected tool: {missing[0]}")

            to_register: list[McpToolRegistration] = []
            pending_specs: list[ToolSpec] = []
            for tool in server.tools:
                existing_tool = await _tool_state(connection, tool, principal)
                if existing_tool:
                    response.existing_tools += 1
                    response.items.append(CommonMcpItem(kind="TOOL", server=server.display_name, name=tool.display_name, status="EXISTING", resource_id=existing_tool.resource_id, resource_version_id=existing_tool.resource_version_id))
                    continue
                slug_owner = next((definition for definition in await registry.list_definitions(principal, ResourceType.TOOL) if definition.slug == tool.slug), None)
                if slug_owner is not None:
                    raise ApiError(409, "COMMON_MCP_TOOL_SLUG_CONFLICT", f"reserved MCP tool slug is already used: {tool.slug}")
                to_register.append(_tool_governance(tool, principal))
                pending_specs.append(tool)

            if to_register:
                published = await register_discovered_tools_batch(RegisterDiscoveredToolsRequest(connection_version_id=connection.resource_version_id, tools=to_register), principal)
                for spec, version in zip(pending_specs, published, strict=True):
                    response.created_tools += 1
                    response.items.append(CommonMcpItem(kind="TOOL", server=server.display_name, name=spec.display_name, status="CREATED", resource_id=version.resource_id, resource_version_id=version.resource_version_id))
        except Exception as exc:
            response.failed += 1
            message = exc.message if isinstance(exc, ApiError) else f"{type(exc).__name__}: {exc}"
            response.items.append(CommonMcpItem(kind="CONNECTION", server=server.display_name, name=server.display_name, status="FAILED", message=message))
    return response
