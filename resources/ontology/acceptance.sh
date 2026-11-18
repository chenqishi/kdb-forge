#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8003}"
H=(-H 'Content-Type: application/json')
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
kdb_seed_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
jq '{data_json: ., status: "active", audit_status: "approved"}' "$kdb_seed_root/global_base.v1.json" > "$D/global.request.json"
jq '{data_json: ., status: "active", audit_status: "approved"}' "$kdb_seed_root/ecommerce_industry.v1.json" > "$D/industry.request.json"
jq '{data_json: .}' "$kdb_seed_root/customer_wayfair.v1.json" > "$D/customer.request.json"

# 1 全局行
curl -sS "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/global.request.json" | jq -e '.success == true and (.ontology | has("data_json") | not)'
# 2 行业行
curl -sS "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/industry.request.json" | jq -e '.success == true'
# 3 客户行（默认启用、未审核），保存响应供后续步骤取 id 与 revision
curl -sS "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/customer.request.json" > "$D/customer.json"
jq -e '.ontology.status == "active" and .ontology.audit_status == "pending"' "$D/customer.json"
# 4 同业务键重复创建为 409
code=$(curl -sS -o "$D/dup.json" -w '%{http_code}' "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/customer.request.json")
[ "$code" = "409" ] && jq -e '.code == "ONTOLOGY_NAME_CONFLICT"' "$D/dup.json"
# 5 未审核时 select_ontology 落到行业行
curl -sS "${H[@]}" -X POST "$BASE/select_ontology" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "industry" and .fallback == true'
# 6 审核通过客户行
ID=$(jq -r '.ontology.ontology_id' "$D/customer.json")
REV=$(jq -r '.ontology.revision' "$D/customer.json")
jq -n --arg id "$ID" --argjson revision "$REV" '{ontology_id:$id,audit_status:"approved",revision:$revision}' > "$D/status.json"
curl -sS "${H[@]}" -X POST "$BASE/update_ontology" -d @"$D/status.json" \
  | jq -e '.ontology.status == "active" and .ontology.audit_status == "approved"'
# 7 审核通过后 select_ontology 返回客户行
curl -sS "${H[@]}" -X POST "$BASE/select_ontology" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "client_product" and .fallback == false'
# 8 只传 client 时为回落语义
curl -sS "${H[@]}" -X POST "$BASE/select_ontology" -d '{"client":"wayfair"}' | jq -e '.fallback == true'
# 9 旧 revision 的 update_ontology 为 409；创建响应只含meta，文档从原请求取得
jq --arg id "$ID" '{ontology_id:$id,data_json:.data_json,revision:1}' "$D/customer.request.json" > "$D/update.json"
code=$(curl -sS -o "$D/conflict.json" -w '%{http_code}' "${H[@]}" -X POST "$BASE/update_ontology" \
  -d @"$D/update.json")
[ "$code" = "409" ] && jq -e '.code == "ONTOLOGY_REVISION_CONFLICT"' "$D/conflict.json"
# 10 软删后 select_ontology 回落行业行；ID和revision放JSON body
jq -n --arg id "$ID" '{ontology_id:$id,revision:2}' > "$D/delete.json"
curl -sS "${H[@]}" -X POST "$BASE/delete_ontology" -d @"$D/delete.json" | jq -e '.deleted == true'
curl -sS "${H[@]}" -X POST "$BASE/select_ontology" \
  -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "industry"'
# 11 删后可重建（同一业务键，判重不含软删行）
curl -sS "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/customer.request.json" > "$D/customer.new.json"
jq -e '.success == true' "$D/customer.new.json"
# 12 同名不同 product 允许并存（业务键含 product），验证后清掉
jq '.data_json.product = "retail"' "$D/customer.request.json" > "$D/retail.json"
curl -sS "${H[@]}" -X POST "$BASE/insert_ontology" -d @"$D/retail.json" > "$D/retail.json.resp"
jq -e '.success == true' "$D/retail.json.resp"
jq '.ontology | {ontology_id,revision}' "$D/retail.json.resp" > "$D/retail.delete.json"
curl -sS "${H[@]}" -X POST "$BASE/delete_ontology" -d @"$D/retail.delete.json" | jq -e '.deleted == true'
# 13 元信息
curl -sS "$BASE/ontology_meta" | jq -e '.limits.max_document_bytes == 1048576'


# 14 默认查询排除未审核，显式审核筛选可查看
jq '.ontology | {ontology_id}' "$D/customer.new.json" > "$D/get.json"
code=$(curl -sS -o "$D/hidden.json" -w '%{http_code}' "${H[@]}" -X POST "$BASE/get_ontology" -d @"$D/get.json")
[ "$code" = "404" ]
curl -sS "${H[@]}" -X POST "$BASE/get_ontology?audit_status=pending" -d @"$D/get.json" | jq -e '.ontology.audit_status == "pending"'
curl -sS -X POST "$BASE/list_ontologies?client=wayfair" | jq -e '.total == 0'
curl -sS -X POST "$BASE/list_ontologies?client=wayfair&audit_status=pending" | jq -e '.total == 1'
# 15 单独审核与停用相互独立，停用但已审核仍可管理查询
jq '.ontology | {ontology_id,revision,audit_status:"approved"}' "$D/customer.new.json" > "$D/status.json"
curl -sS "${H[@]}" -X POST "$BASE/update_ontology" -d @"$D/status.json" > "$D/approved.json"
jq '.ontology | {ontology_id,revision,status:"inactive"}' "$D/approved.json" > "$D/status.json"
curl -sS "${H[@]}" -X POST "$BASE/update_ontology" -d @"$D/status.json" > "$D/inactive.json"
jq -e '.ontology.status == "inactive" and .ontology.audit_status == "approved"' "$D/inactive.json"
curl -sS "${H[@]}" -X POST "$BASE/get_ontology" -d @"$D/get.json" | jq -e '.ontology.status == "inactive"'
curl -sS "${H[@]}" -X POST "$BASE/select_ontology" -d '{"client":"wayfair","product":"ecommerce"}' | jq -e '.scope == "industry"'
# 16 正文替换默认回到未审核，生效状态保持停用
jq -n --slurpfile row "$D/inactive.json" --slurpfile source "$D/customer.request.json" \
  '{ontology_id:$row[0].ontology.ontology_id,revision:$row[0].ontology.revision,data_json:($source[0].data_json + {description:"重新审核"})}' > "$D/update.json"
curl -sS "${H[@]}" -X POST "$BASE/update_ontology" -d @"$D/update.json" > "$D/edited.json"
jq -e '.ontology.status == "inactive" and .ontology.audit_status == "pending"' "$D/edited.json"
curl -sS -X POST "$BASE/list_ontologies?client=wayfair" | jq -e '.total == 0'
# 17 软删与审核筛选独立；未审核记录可直接软删
jq '.ontology | {ontology_id,revision}' "$D/edited.json" > "$D/delete.json"
curl -sS "${H[@]}" -X POST "$BASE/delete_ontology" -d @"$D/delete.json" | jq -e '.deleted == true and .ontology.audit_status == "pending"'
code=$(curl -sS -o "$D/deleted.json" -w '%{http_code}' "${H[@]}" -X POST "$BASE/get_ontology?include_deleted=true" -d @"$D/get.json")
[ "$code" = "404" ]
curl -sS "${H[@]}" -X POST "$BASE/get_ontology?include_deleted=true&audit_status=all" -d @"$D/get.json" | jq -e '.ontology.del_flag == 1'

printf "Ontology acceptance: 17 steps passed\n"
