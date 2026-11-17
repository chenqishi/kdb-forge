#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8003}"
H=(-H 'Content-Type: application/json')
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
kdb_seed_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
jq '{data_json: ., status: "active"}' "$kdb_seed_root/global_base.v1.json" > "$D/global.request.json"
jq '{data_json: ., status: "active"}' "$kdb_seed_root/ecommerce_industry.v1.json" > "$D/industry.request.json"
jq '{data_json: ., status: "draft"}' "$kdb_seed_root/customer_wayfair.v1.json" > "$D/customer.request.json"

# 1 全局行
curl -sS "${H[@]}" -X POST "$BASE/ontology" -d @"$D/global.request.json" | jq -e '.success == true'
# 2 行业行
curl -sS "${H[@]}" -X POST "$BASE/ontology" -d @"$D/industry.request.json" | jq -e '.success == true'
# 3 客户行（draft），保存响应供后续步骤取 id 与 revision
curl -sS "${H[@]}" -X POST "$BASE/ontology" -d @"$D/customer.request.json" > "$D/customer.json"
jq -e '.ontology.status == "draft"' "$D/customer.json"
# 4 同业务键重复创建为 409
code=$(curl -sS -o "$D/dup.json" -w '%{http_code}' "${H[@]}" -X POST "$BASE/ontology" -d @"$D/customer.request.json")
[ "$code" = "409" ] && jq -e '.code == "ONTOLOGY_NAME_CONFLICT"' "$D/dup.json"
# 5 未激活时 resolve 落到行业行
curl -sS "${H[@]}" -X POST "$BASE/ontology/resolve" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "industry" and .fallback == true'
# 6 激活客户行
ID=$(jq -r '.ontology.ontology_id' "$D/customer.json")
REV=$(jq -r '.ontology.revision' "$D/customer.json")
curl -sS "${H[@]}" -X PATCH "$BASE/ontology/$ID" -d "{\"status\":\"active\",\"revision\":$REV}" \
  | jq -e '.ontology.status == "active"'
# 7 激活后 resolve 返回客户行
curl -sS "${H[@]}" -X POST "$BASE/ontology/resolve" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "client_product" and .fallback == false'
# 8 只传 client 时为回落语义
curl -sS "${H[@]}" -X POST "$BASE/ontology/resolve" -d '{"client":"wayfair"}' | jq -e '.fallback == true'
# 9 旧 revision 的 PUT 为 409
DOC=$(jq -c '.ontology.data_json' "$D/customer.json")
code=$(curl -sS -o "$D/conflict.json" -w '%{http_code}' "${H[@]}" -X PUT "$BASE/ontology/$ID" \
  -d "{\"data_json\":$DOC,\"revision\":1}")
[ "$code" = "409" ] && jq -e '.code == "ONTOLOGY_REVISION_CONFLICT"' "$D/conflict.json"
# 10 软删后 resolve 回落行业行
curl -sS -X DELETE "$BASE/ontology/$ID" | jq -e '.deleted == true'
curl -sS "${H[@]}" -X POST "$BASE/ontology/resolve" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "industry"'
# 11 删后可重建（同一业务键，判重不含软删行）
curl -sS "${H[@]}" -X POST "$BASE/ontology" -d @"$D/customer.request.json" | jq -e '.success == true'
# 12 同名不同 product 允许并存（业务键含 product），验证后清掉
jq '.data_json.product = "retail"' "$D/customer.request.json" > "$D/retail.json"
curl -sS "${H[@]}" -X POST "$BASE/ontology" -d @"$D/retail.json" > "$D/retail.json.resp"
jq -e '.success == true' "$D/retail.json.resp"
RID=$(jq -r '.ontology.ontology_id' "$D/retail.json.resp")
curl -sS -X DELETE "$BASE/ontology/$RID" | jq -e '.deleted == true'
# 13 元信息
curl -sS "$BASE/ontology/meta" | jq -e '.limits.max_document_bytes == 1048576'


printf "Ontology acceptance: 13 steps passed\n"
