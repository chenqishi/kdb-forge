# kdb.mining.chat.identity.load_contact_identity_lookup

## Signature

`load_contact_identity_lookup(mysql_config_file='config/mysql_conn_config.json')`

## Inputs

mysql_config_file，默认 config/mysql_conn_config.json。

## Outputs

构建通讯录身份查找表；ID 优先，姓名作为同事/leader 回退；缺配置返回空 lookup。

## SQL

以下表和字段来自当前函数内实际 SQL，未提供完整 DDL：

```sql
SELECT
                we_com_contact_user_id,
                we_com_contact_nick_name,
                we_com_contact_real_name,
                we_com_contact_relationship,
                we_com_contact_relation_type
            FROM rf_wkt_we_com_contact
            WHERE (del_flag IS NULL OR del_flag = 0)
              AND (is_enabled IS NULL OR is_enabled = 1)
```

```sql
SELECT
                address_wc_id,
                address_wechat_number,
                address_nick_name,
                relationship
            FROM rf_wkt_wechat_address
            WHERE (del_flag IS NULL OR del_flag = 0)
              AND (is_enabled IS NULL OR is_enabled = 1)
```

## Source

`src/kdb/mining/chat/identity.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
