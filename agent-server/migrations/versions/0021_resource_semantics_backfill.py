"""Backfill readable semantics for existing resources.

Revision ID: 0021_resource_semantics_backfill
Revises: 0020_resource_semantics
"""
from alembic import op


revision = "0021_resource_semantics_backfill"
down_revision = "0020_resource_semantics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE platform_resource_descriptor d
        SET one_line_summary = COALESCE(NULLIF(r.description, ''), r.display_name || '（' || r.resource_type || '）'),
            when_to_use = CASE r.resource_type
                WHEN 'PROMPT' THEN '需要定义智能体角色、回答风格和行为边界时'
                WHEN 'SKILL' THEN '任务符合该技能的业务流程，并需要组合其 Tool 或 Knowledge 依赖时'
                WHEN 'TOOL' THEN '智能体需要调用该受控工具获取或处理业务数据时'
                WHEN 'KNOWLEDGE' THEN '回答需要依据该知识库中的企业文档时'
                WHEN 'MEMORY_POLICY' THEN '智能体需要跨会话保留当前用户显式记忆时'
                WHEN 'MCP_CONNECTION' THEN '平台需要连接 MCP 服务并发现可注册 Tool 时'
                ELSE '业务场景与该资源说明一致时' END,
            when_not_to_use = CASE WHEN r.resource_type = 'MCP_CONNECTION'
                THEN '不直接组装进 Agent；应先发现并注册为 Tool'
                ELSE '当任务超出该资源的说明、授权或风险边界时' END,
            input_summary = CASE r.resource_type
                WHEN 'PROMPT' THEN '系统级角色与行为指令'
                WHEN 'SKILL' THEN '业务任务和 Skill 所依赖的 Tool/Knowledge 上下文'
                WHEN 'TOOL' THEN '符合该 Tool Schema 的结构化参数'
                WHEN 'KNOWLEDGE' THEN '用户问题或检索查询'
                WHEN 'MEMORY_POLICY' THEN '当前 Deployment、RuoYi 用户和显式记忆内容'
                ELSE '见该资源的专属配置' END,
            output_summary = CASE r.resource_type
                WHEN 'PROMPT' THEN '注入 Runtime 的系统提示词'
                WHEN 'SKILL' THEN '组合后的业务指令和依赖能力'
                WHEN 'TOOL' THEN 'Tool 调用的结构化结果'
                WHEN 'KNOWLEDGE' THEN '带文档溯源的相关知识分块'
                WHEN 'MEMORY_POLICY' THEN '符合 TTL、分类和数量限制的用户长期记忆'
                ELSE '见该资源的专属配置' END
        FROM platform_resource_definition r
        WHERE d.tenant_id = r.tenant_id AND d.resource_id = r.resource_id
          AND (d.one_line_summary IS NULL OR d.when_to_use IS NULL OR d.input_summary IS NULL OR d.output_summary IS NULL)
    """)
    op.execute("""
        UPDATE platform_resource_descriptor d
        SET one_line_summary = m.display_name || '：' || COALESCE(m.config->>'model', 'OpenAI Compatible Model'),
            when_to_use = CASE WHEN m.config->>'model_mode' = 'EMBEDDING' THEN '需要为知识文档和查询生成向量时' ELSE '智能体需要对话推理、回答或 Tool Calling 时' END,
            when_not_to_use = CASE WHEN m.config->>'model_mode' = 'EMBEDDING' THEN '不用于生成对话回答' ELSE '不用于生成知识库向量' END,
            input_summary = CASE WHEN m.config->>'model_mode' = 'EMBEDDING' THEN '待向量化的文本列表' ELSE '对话消息、系统指令和可用 Tool Schema' END,
            output_summary = CASE WHEN m.config->>'model_mode' = 'EMBEDDING' THEN '文本对应的向量' ELSE '模型回答或 Tool Call' END
        FROM platform_model_definition m
        WHERE d.tenant_id = m.tenant_id AND d.resource_id = m.model_id
          AND (d.one_line_summary IS NULL OR d.when_to_use IS NULL OR d.input_summary IS NULL OR d.output_summary IS NULL)
    """)


def downgrade() -> None:
    pass
