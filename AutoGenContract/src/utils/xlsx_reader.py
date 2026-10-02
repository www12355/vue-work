"""读取 templates/replace.xlsx 占位符映射表。"""

import os
from typing import Dict, List, Optional
import openpyxl


class PlaceholderMap:
    """读取 replace.xlsx 并提供占位符 → 中文描述的双向映射。

    LLM_FIELDS: 需要大语言模型生成的 5 个关键占位符。
    """

    LLM_FIELDS = {
        "aicc_service_content",
        "aicc_searcher_protected_content",
        "aicc_provider_protected_content",
        "aicc_service_fee",
        "aicc_delete_provide_condition",
    }

    def __init__(self, xlsx_path: str):
        """
        Args:
            xlsx_path: replace.xlsx 文件的绝对路径
        """
        if not os.path.exists(xlsx_path):
            raise FileNotFoundError(f"占位符映射文件不存在: {xlsx_path}")

        self._map: Dict[str, str] = {}
        self._load(xlsx_path)

    def _load(self, xlsx_path: str):
        """从 Excel 文件加载占位符映射。

        期望格式：第一列为 placeholder（含 {{ }}），第二列为描述。
        跳过空行和标题行。
        """
        wb = openpyxl.load_workbook(xlsx_path, read_only=True)
        ws = wb.active

        for row in ws.iter_rows(min_row=2, max_col=2, values_only=True):
            placeholder = row[0]
            description = row[1]
            if placeholder and description:
                # 规范化占位符名称（去掉 {{ }}）
                name = str(placeholder).strip()
                if name.startswith("{{") and name.endswith("}}"):
                    name = name[2:-2]
                self._map[name] = str(description).strip()

        wb.close()

    def get_description(self, placeholder: str) -> str:
        """获取占位符对应的中文描述。

        Args:
            placeholder: 占位符名称（不含或含 {{ }}）

        Returns:
            中文描述字符串，找不到时返回占位符名称本身
        """
        name = placeholder.strip()
        if name.startswith("{{") and name.endswith("}}"):
            name = name[2:-2]
        return self._map.get(name, name)

    def is_llm_field(self, placeholder: str) -> bool:
        """判断占位符是否需要 LLM 生成。

        Args:
            placeholder: 占位符名称
        """
        name = placeholder.strip()
        if name.startswith("{{") and name.endswith("}}"):
            name = name[2:-2]
        return name in self.LLM_FIELDS

    def get_all_placeholders(self) -> Dict[str, str]:
        """获取完整的占位符 → 描述映射。"""
        return dict(self._map)

    def get_llm_fields(self) -> List[str]:
        """获取需要 LLM 生成的占位符名称列表。"""
        return sorted(self.LLM_FIELDS)
