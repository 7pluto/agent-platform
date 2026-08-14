#!/usr/bin/env bash
set -euo pipefail

platform="http://127.0.0.1:8000/api/v1"
cookies="$(mktemp)"
login_json="$(mktemp)"
payload="$(mktemp)"
result="$(mktemp)"
trap 'rm -f "$cookies" "$login_json" "$payload" "$result"' EXIT
chmod 600 "$cookies" "$login_json" "$payload" "$result"

curl -fsS -c "$cookies" -b "$cookies" -H 'Content-Type: application/json' \
  -d '{"ticket_code":"dev-ticket"}' "$platform/auth/exchange" >"$login_json"
csrf="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "$login_json")"

api_key="$(sudo docker exec docker-api-1 python -c '
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from models.engine import db
from models.provider import ProviderCredential
from core.helper import encrypter
from app_factory import create_app
tenant_id="7080ce31-1263-45b6-9b29-d9d35c8f2678"
_, app = create_app()
with app.app_context():
  with Session(db.engine) as session:
      row=session.execute(select(ProviderCredential).where(ProviderCredential.tenant_id==tenant_id, ProviderCredential.provider_name=="langgenius/siliconflow/siliconflow")).scalar_one()
      token=json.loads(row.encrypted_config)["api_key"]
  print(encrypter.decrypt_token(tenant_id=tenant_id, token=token), end="")
')"

create_model() {
  local slug="$1" name="$2" model="$3" mode="$4"
  python3 - "$api_key" "$payload" "$slug" "$name" "$model" "$mode" <<'PY'
import json, sys
json.dump({"slug":sys.argv[3],"display_name":sys.argv[4],"base_url":"https://api.siliconflow.cn/v1","model":sys.argv[5],"api_key":sys.argv[1],"model_mode":sys.argv[6]}, open(sys.argv[2],"w",encoding="utf-8"), ensure_ascii=False)
PY
  http="$(curl -sS -o "$result" -w '%{http_code}' -c "$cookies" -b "$cookies" -H "X-CSRF-Token: ${csrf}" -H 'Content-Type: application/json' --data-binary "@$payload" "$platform/models/with-secret")"
  python3 - "$http" "$result" <<'PY'
import json,sys
p=json.load(open(sys.argv[2],encoding="utf-8"))
print(json.dumps({"http_status":sys.argv[1],"model_version_id":p.get("model_version_id"),"model_id":p.get("model_id"),"status":p.get("status"),"availability":p.get("availability"),"model":(p.get("config") or {}).get("model"),"model_mode":(p.get("config") or {}).get("model_mode"),"secret_ref":(p.get("config") or {}).get("secret_ref")},ensure_ascii=False))
PY
  test "$http" = 201
}

create_model siliconflow-qwen3-8b "SiliconFlow Qwen3 8B" "Qwen/Qwen3-8B" CHAT
create_model siliconflow-bge-large-zh "SiliconFlow BGE Large ZH" "BAAI/bge-large-zh-v1.5" EMBEDDING
unset api_key
