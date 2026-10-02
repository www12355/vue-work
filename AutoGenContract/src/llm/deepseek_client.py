"""DeepSeek API 客户端模块。

基于 OpenAI-compatible API 封装，支持：
- 流式响应（实时回调进度）
- 指数退避重试（最多 2 次）
- 连接测试
"""

import logging
import time
from typing import Callable, Optional, Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用基础错误。"""
    pass


class LLMConnectionError(LLMError):
    """无法连接到 API。"""
    pass


class LLMResponseError(LLMError):
    """API 返回了错误响应。"""
    pass


class LLMConfigError(LLMError):
    """API 配置错误（如无效的 API Key）。"""
    pass


class DeepSeekClient:
    """DeepSeek API 客户端。

    使用 OpenAI-compatible 接口调用 DeepSeek 模型。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: DeepSeek 配置字典，包含:
                - api_key: API 密钥
                - base_url: API 端点
                - model: 模型名称
                - temperature: 温度参数
                - max_tokens: 最大输出 token 数
                - timeout: 请求超时（秒）
        """
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.deepseek.com")
        self.model = config.get("model", "deepseek-chat")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 4096)
        self.timeout = config.get("timeout", 120)

        if not self.api_key or self.api_key == "sk-your-api-key-here":
            raise LLMConfigError(
                "API Key 未配置。请在 config.yaml 的 deepseek.api_key 字段填写有效的 API Key。"
            )

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,  # 我们自己处理重试
        )

        logger.info(
            f"DeepSeek 客户端已初始化: model={self.model}, "
            f"base_url={self.base_url}"
        )

    def generate(
        self,
        section_name: str,
        system_prompt: str,
        user_prompt: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        max_retries: int = 2,
    ) -> str:
        """调用 DeepSeek API 生成文本（流式模式）。

        Args:
            section_name: 章节名称（用于日志）
            system_prompt: 系统指令
            user_prompt: 用户 Prompt
            progress_callback: 流式回调函数，接收增量文本块
            max_retries: 最大重试次数

        Returns:
            生成的完整文本

        Raises:
            LLMConnectionError: 网络连接失败
            LLMResponseError: API 返回错误
            LLMConfigError: API Key 无效
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"[{section_name}] 开始生成 (尝试 {attempt + 1}/{max_retries + 1})"
                )

                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True,
                )

                full_text = ""
                chunk_count = 0
                for chunk in response:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            chunk_text = delta.content
                            full_text += chunk_text
                            chunk_count += 1
                            if progress_callback:
                                progress_callback(chunk_text)

                logger.info(
                    f"[{section_name}] 生成完成: {len(full_text)} 字符, "
                    f"{chunk_count} 个流式块"
                )

                # 验证输出长度
                if len(full_text.strip()) < 50:
                    logger.warning(
                        f"[{section_name}] 生成文本过短 ({len(full_text)} 字符), "
                        f"可能需要重试"
                    )
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue

                return full_text

            except Exception as e:
                last_error = e
                error_str = str(e)

                # 判断错误类型
                if "401" in error_str or "unauthorized" in error_str.lower():
                    raise LLMConfigError(
                        f"API Key 无效或已过期。请检查 config.yaml 中的 api_key。\n"
                        f"原始错误: {e}"
                    ) from e

                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < max_retries:
                        wait = 2 ** (attempt + 1)
                        logger.warning(
                            f"[{section_name}] 频率限制，等待 {wait} 秒后重试..."
                        )
                        time.sleep(wait)
                        continue
                    raise LLMResponseError(
                        f"API 请求频率过高，请稍后重试。\n原始错误: {e}"
                    ) from e

                if "timeout" in error_str.lower() or "connect" in error_str.lower():
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        logger.warning(
                            f"[{section_name}] 连接超时，等待 {wait} 秒后重试..."
                        )
                        time.sleep(wait)
                        continue
                    raise LLMConnectionError(
                        f"无法连接到 DeepSeek API。请检查网络连接。\n原始错误: {e}"
                    ) from e

                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        f"[{section_name}] 生成失败: {e}, "
                        f"等待 {wait} 秒后重试..."
                    )
                    time.sleep(wait)
                    continue

                raise LLMResponseError(
                    f"DeepSeek API 调用失败: {e}"
                ) from e

        # 所有重试均失败
        if isinstance(last_error, LLMError):
            raise last_error
        raise LLMResponseError(f"生成失败（已重试 {max_retries} 次）: {last_error}")

    def test_connection(self, timeout: int = 10) -> bool:
        """测试 API 连接是否正常。

        Args:
            timeout: 超时秒数（默认 10 秒，比普通请求更短以避免长时间阻塞）

        Returns:
            True 表示连接正常，False 表示连接失败
        """
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Hello"},
                ],
                max_tokens=5,
                temperature=0,
                stream=False,
                timeout=timeout,
            )
            if response.choices and len(response.choices) > 0:
                logger.info("API 连接测试成功")
                return True
            return False
        except Exception as e:
            logger.error(f"API 连接测试失败: {e}")
            return False
