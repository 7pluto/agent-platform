import asyncio
import json

from app.api.routes.workbench import _catalog
from app.iam.models import Principal


async def main() -> None:
    principal = Principal(
        provider="verification", external_user_id="1", external_org_id="org-demo",
        tenant_id="tenant-demo", display_name="verification", role_codes=("admin",), dept_ids=(),
    )
    items = await _catalog(principal)
    print(json.dumps({
        "published": len(items),
        "with_summary": sum(bool(item.one_line_summary) for item in items),
        "with_when_to_use": sum(bool(item.when_to_use) for item in items),
        "with_input_output": sum(bool(item.input_summary and item.output_summary) for item in items),
        "risk_classified": sum(item.risk_level in {"LOW", "MEDIUM", "HIGH"} for item in items),
    }, ensure_ascii=False))


asyncio.run(main())
