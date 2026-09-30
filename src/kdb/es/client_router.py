"""按索引选择 Elasticsearch 8.17 客户端。

Aliyun Elasticsearch Serverless 与 PaaS 的查询 DSL、mapping 和认证方式在本项目中
保持一致，差异主要是服务地址。因此这里把地址选择集中到一个小的路由层，业务层只
需要调用 ``get_client_by_index(index_name)``。
"""

from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

_PROVIDER_ALIASES = {
    "pass": "paas",
    "paas": "paas",
    "serverless": "serverless",
    "server-less": "serverless",
}

_CLIENT_OPTION_KEYS = {
    "request_timeout",
    "max_retries",
    "retry_on_timeout",
    "verify_certs",
    "ca_certs",
    "client_cert",
    "client_key",
    "ssl_assert_fingerprint",
    "http_compress",
    "headers",
}


def _normalise_provider_name(name: str) -> str:
    """将 provider 别名统一为配置内部使用的名称。"""
    value = str(name or "").strip().lower()
    return _PROVIDER_ALIASES.get(value, value)


def _normalise_hosts(value: Any) -> List[str]:
    """把 host/hosts 配置统一为非空字符串列表。"""
    if isinstance(value, str):
        hosts = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        hosts = [str(item).strip() for item in value if str(item).strip()]
    else:
        hosts = []
    return hosts


class IndexClientRouter:
    """根据索引名缓存并返回 Elasticsearch 8.17 客户端。

    配置支持以下形式，旧的单地址配置也继续可用：

    .. code-block:: json

       {
         "es_version": "8.17",
         "default_provider": "serverless",
         "providers": {
           "serverless": {"hosts": ["https://..."], "username": "...", "password": "..."},
           "paas": {"hosts": ["https://..."], "username": "...", "password": "..."}
         },
         "index_routes": {"qa_a": "serverless", "qa_b": "paas"}
       }

    ``index_routes`` 的键支持 ``fnmatch`` 通配符，例如 ``tenant_*``。精确索引名
    优先于通配规则；未命中的索引使用 ``default_provider``。
    """

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        config_path: Optional[str] = None,
        client_factory: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    ) -> None:
        """初始化路由器。

        Args:
            config: 已加载的 ES 配置；与 config_path 二选一。
            config_path: JSON 配置文件路径。
            client_factory: 测试注入点，接收单个 provider 配置并返回 client。
        """
        if config is not None and config_path is not None:
            raise ValueError("config 与 config_path 只能指定一个")
        if config_path:
            with Path(config_path).open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        self.config: Dict[str, Any] = dict(config or {})
        self._providers = self._parse_providers(self.config)
        self._routes = self._parse_routes(self.config)
        self._default_provider = self._resolve_default_provider(self.config)
        if self._default_provider not in self._providers:
            raise ValueError(
                f"default_provider={self._default_provider!r} 未配置，可选: "
                f"{sorted(self._providers)}"
            )
        self._client_factory = client_factory or self._create_client
        self._clients: Dict[str, Any] = {}

    @staticmethod
    def _parse_providers(config: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        """读取 providers，并兼容单地址及顶层 serverless/paas 配置。"""
        raw_providers = config.get("providers") or config.get("endpoints") or {}
        providers: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw_providers, Mapping):
            for name, provider_config in raw_providers.items():
                if isinstance(provider_config, Mapping):
                    providers[_normalise_provider_name(str(name))] = dict(provider_config)

        for name in ("serverless", "paas", "pass"):
            provider_config = config.get(name)
            if isinstance(provider_config, Mapping):
                providers.setdefault(_normalise_provider_name(name), dict(provider_config))

        if not providers and (config.get("hosts") or config.get("host")):
            providers["default"] = dict(config)

        if not providers:
            raise ValueError("ES 配置缺少 hosts，或缺少 providers 中的有效 provider")
        return providers

    @staticmethod
    def _parse_routes(config: Mapping[str, Any]) -> Dict[str, str]:
        """读取 index_routes，并兼容常见的旧字段名。"""
        raw_routes = (
            config.get("index_routes")
            or config.get("index_to_provider")
            or config.get("index_provider_map")
            or config.get("index_to_endpoint")
            or {}
        )
        routes: Dict[str, str] = {}
        if not isinstance(raw_routes, Mapping):
            raise ValueError("index_routes 必须是对象，格式为 {index_name: provider}")
        for index_name, provider in raw_routes.items():
            if isinstance(provider, Mapping):
                provider = provider.get("provider") or provider.get("endpoint") or provider.get("type")
            if not provider:
                raise ValueError(f"索引 {index_name!r} 没有 provider")
            routes[str(index_name).strip().lower()] = _normalise_provider_name(str(provider))
        return routes

    def _resolve_default_provider(self, config: Mapping[str, Any]) -> str:
        """解析默认 provider，未设置时使用第一个 provider。"""
        configured = (
            config.get("default_provider")
            or config.get("default_endpoint")
            or config.get("default_index_provider")
        )
        if configured:
            return _normalise_provider_name(str(configured))
        return next(iter(self._providers))

    @property
    def providers(self) -> Dict[str, Dict[str, Any]]:
        """返回脱敏后的 provider 配置，便于诊断但不暴露凭据或 client。"""
        secret_keys = {"password", "api_key", "client_key"}
        return {
            name: {
                key: "<redacted>" if key in secret_keys else value
                for key, value in provider_config.items()
            }
            for name, provider_config in self._providers.items()
        }

    def resolve_provider(self, index_name: str) -> str:
        """根据索引名解析 provider。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        exact = self._routes.get(index)
        if exact:
            provider = exact
        else:
            provider = self._default_provider
            # 保持配置顺序；精确规则已经在上面优先处理。
            for pattern, candidate in self._routes.items():
                if "*" in pattern or "?" in pattern or "[" in pattern:
                    if fnmatch.fnmatchcase(index, pattern):
                        provider = candidate
                        break
        if provider not in self._providers:
            raise ValueError(
                f"索引 {index!r} 路由到未配置的 provider {provider!r}，可选: "
                f"{sorted(self._providers)}"
            )
        return provider

    def get_client_by_index(self, index_name: str) -> Any:
        """返回索引对应的缓存 client；同一 provider 只创建一个连接池。"""
        provider = self.resolve_provider(index_name)
        if provider not in self._clients:
            self._clients[provider] = self._client_factory(self._providers[provider])
            logger.info("ES index route initialized: index=%s provider=%s", index_name, provider)
        return self._clients[provider]

    def _create_client(self, provider_config: Mapping[str, Any]) -> Any:
        """用 ES Python client 8.x 创建一个 provider client。"""
        from elasticsearch import Elasticsearch

        hosts = _normalise_hosts(
            provider_config.get("hosts")
            or provider_config.get("host")
            or provider_config.get("endpoint")
            or provider_config.get("url")
        )
        if not hosts:
            raise ValueError("provider 配置缺少 hosts")

        options: Dict[str, Any] = {
            "hosts": hosts,
            "request_timeout": provider_config.get(
                "request_timeout", provider_config.get("timeout", 30)
            ),
            "max_retries": provider_config.get("max_retries", 3),
            "retry_on_timeout": provider_config.get("retry_on_timeout", True),
            "verify_certs": provider_config.get("verify_certs", False),
        }
        username = provider_config.get("username")
        password = provider_config.get("password")
        if username is not None and password is not None:
            options["basic_auth"] = (username, password)
        if provider_config.get("api_key") is not None:
            options["api_key"] = provider_config["api_key"]

        custom_options: Dict[str, Any] = {}
        for option_key in _CLIENT_OPTION_KEYS:
            if option_key in provider_config:
                custom_options[option_key] = provider_config[option_key]
        for option_group in (provider_config.get("client_options"), provider_config.get("extra_params")):
            if isinstance(option_group, Mapping):
                custom_options.update(
                    {
                        key: value
                        for key, value in option_group.items()
                        if key in _CLIENT_OPTION_KEYS
                    }
                )
        options.update(custom_options)
        return Elasticsearch(**options)

    def close(self) -> None:
        """关闭所有已创建的 client。"""
        for client in self._clients.values():
            close = getattr(client, "close", None)
            if close:
                close()
        self._clients.clear()


__all__ = ["IndexClientRouter"]
