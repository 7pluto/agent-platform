import asyncio
import json

from app.api.routes.workbench import _catalog, workbench_resource_detail, workbench_resources
from app.iam.models import Principal


async def main() -> None:
    principal = Principal(
        provider="stage46-verification",
        external_user_id="1",
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name="Stage 4.6 Verification",
        role_codes=("admin",),
        dept_ids=(),
    )
    page = await workbench_resources(
        query=None,
        resource_type=None,
        status=None,
        page=1,
        page_size=100,
        principal=principal,
    )
    catalog = await _catalog(principal)
    model = next(item for item in page.items if item.resource_type == "MODEL" and item.latest_version_number)
    dependent = next(item for item in catalog if item.dependencies)
    model_detail = await workbench_resource_detail(model.resource_id, principal)
    dependency_detail = await workbench_resource_detail(dependent.resource_id, principal)
    print(json.dumps({
        "resource_definitions": page.meta.total,
        "types": sorted({item.resource_type for item in page.items}),
        "model_detail": {
            "name": model_detail.resource.display_name,
            "versions": len(model_detail.versions),
            "source": model_detail.source,
        },
        "dependency_detail": {
            "name": dependency_detail.resource.display_name,
            "dependencies": [dependency["display_name"]
                             for node in dependency_detail.dependency_graph
                             for dependency in node["dependencies"]],
        },
    }, ensure_ascii=False, indent=2))


asyncio.run(main())
