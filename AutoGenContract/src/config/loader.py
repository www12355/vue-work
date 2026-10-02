"""YAML 配置文件加载与校验模块。"""

import os
import yaml
from typing import Any, Dict, List, Optional


class ConfigError(Exception):
    """配置错误，阻止程序启动。"""
    pass


class ConfigLoader:
    """加载并校验 config.yaml 配置。"""

    REQUIRED_KEYS = [
        "deepseek.api_key",
        "paths.template",
        "paths.output",
    ]

    def __init__(self, config_path: str):
        """
        Args:
            config_path: config.yaml 的绝对路径
        Raises:
            ConfigError: 配置文件缺失或关键字段无效
        """
        self.config_path = config_path
        self._data: Dict[str, Any] = {}
        self._load()
        self._validate()

    def _load(self):
        """加载 YAML 文件。"""
        if not os.path.exists(self.config_path):
            raise ConfigError(
                f"配置文件不存在: {self.config_path}\n"
                f"请确保 config.yaml 存在于项目根目录。"
            )
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"配置文件解析失败: {e}")

    def _validate(self):
        """校验必填字段。"""
        errors = []
        for key in self.REQUIRED_KEYS:
            if not self._get_nested(key):
                errors.append(f"缺少必填配置项: {key}")
        if errors:
            raise ConfigError("\n".join(errors))

        # 校验 API key 不是默认占位符
        api_key = self.get_deepseek_config().get("api_key", "")
        if not api_key or api_key == "sk-your-api-key-here":
            raise ConfigError(
                "请先在 config.yaml 中填写您的 DeepSeek API Key。\n"
                "在 deepseek.api_key 字段填入有效的 API Key。"
            )

    def _get_nested(self, dotted_key: str, default=None) -> Any:
        """通过点号分隔的键路径获取嵌套字典值。"""
        keys = dotted_key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value

    def get_deepseek_config(self) -> Dict[str, Any]:
        """返回 DeepSeek API 配置字典。"""
        return self._data.get("deepseek", {})

    def get_default_provider(self) -> str:
        """返回乙方公司默认名称。"""
        return self._data.get("defaults", {}).get(
            "provider_name", "天津智算数字产业发展有限公司"
        )

    def get_paths(self) -> Dict[str, str]:
        """返回路径配置字典。"""
        return self._data.get("paths", {})

    def get_gui_config(self) -> Dict[str, Any]:
        """返回 GUI 配置。"""
        return self._data.get("gui", {})

    def get_llm_sections(self) -> List[Dict[str, Any]]:
        """返回 LLM 章节配置列表。"""
        return self._data.get("llm_sections", [])

    def get_logging_config(self) -> Dict[str, Any]:
        """返回日志配置。"""
        return self._data.get("logging", {})

    def get_all(self) -> Dict[str, Any]:
        """返回完整配置数据。"""
        return self._data
