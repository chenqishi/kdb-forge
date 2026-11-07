# api
Inputs: 固定只读路径openapi.json/search/web_search/list_file_names，可选payload。
Outputs: JSON响应、毫秒、响应字节数。timeout30秒、最多8MiB，HTTP非200报错。
仅localhost:8003读接口，不允许insert/delete/update，不涉及SQL。
