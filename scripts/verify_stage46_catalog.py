import asyncio
import json

from app.api.routes.workbench import _catalog
from app.iam.models import Principal


async def main() -> None:
    principal = Principal(
        provider="stage46-verification",
        external_user_id="admin",
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name="Stage 4.6 Verification",
        role_codes=("admin",),
        dept_ids=(),
    )
    items = await _catalog(principal)
    payload = {
        "count": len(items),
        "with_owner": sum(bool(item.owner_user_id) for item in items),
        "with_source": sum(bool(item.source_type) for item in items),
        "with_dependencies": sum(bool(item.dependencies) for item in items),
        "samples": [
            {
                "name": item.display_name,
                "type": item.resource_type,
                "source": item.source_type,
                "owner": item.owner_user_id,
                "version": item.version_number,
                "dependencies": len(item.dependencies),
            }
            for item in items[:10]
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


asyncio.run(main())
