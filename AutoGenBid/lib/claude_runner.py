"""
Claude CLI 运行器 — subprocess 封装，带重试和输出验证。

用法:
    from lib.claude_runner import ClaudeRunner
    runner = ClaudeRunner(cfg)
    ok = runner.run(prompt, out_file)
"""

from __future__ import annotations

import sys
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ClaudeRunner:
    """Claude CLI subprocess 封装器。

    使用 Popen + 读取线程实现实时 stdout/stderr 捕获，
    同时写入工作区日志文件并通过 log_callback 转发。
    """

    def __init__(self, config: Dict[str, Any], skills_dir: Optional[Path] = None, log_callback=None, working_dir: Optional[Path] = None):
        """
        Args:
            config: claude 配置节（来自 pipeline_config.yaml 的 claude: 段）
            skills_dir: skills/ 目录路径（用于 --add-dir）
            log_callback: 可选的回调函数 callable(message) 用于服务器模式日志转发
            working_dir: session workspace 路径，用于 --add-dir 沙箱隔离
        """
        self.cfg = config
        self.timeout = int(config.get("timeout", 600))
        self.max_retries = int(config.get("max_retries", 3))
        self.min_output_size = int(config.get("min_output_size", 200))
        self.allowed_tools = config.get("allowed_tools", ["Read", "Write", "Bash", "Glob", "Grep"])
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self.working_dir = Path(working_dir) if working_dir else None
        self._claude_path: Optional[str] = None
        self.log_callback = log_callback  # callable(message) or None

        # Log directory for Claude output files (per-session)
        self.logs_dir: Optional[Path] = None
        self._log_lock = threading.Lock()  # thread-safe file writes

    @property
    def _logs_dir(self) -> Optional[Path]:
        """Lazy-init the logs directory from working_dir."""
        if self.logs_dir is None and self.working_dir:
            self.logs_dir = self.working_dir / ".cache" / "claude_logs"
        return self.logs_dir

    # ── 查找 Claude ──────────────────────────────────────

    @staticmethod
    def find_claude() -> str:
        """查找 claude CLI 可执行文件路径。"""
        c = shutil.which("claude")
        if c:
            return c
        # Windows 常见安装路径
        home = Path.home()
        candidates = [
            home / "AppData" / "Roaming" / "npm" / "claude.cmd",
            home / "AppData" / "Local" / "npm" / "claude.cmd",
            Path("C:/Program Files/nodejs/claude.cmd"),
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        raise FileNotFoundError(
            "未找到 claude CLI。请安装: npm install -g @anthropic-ai/claude-code"
        )

    @property
    def claude_path(self) -> str:
        if self._claude_path is None:
            self._claude_path = self.find_claude()
        return self._claude_path

    def _log(self, msg: str) -> None:
        """Print and optionally forward log via callback."""
        print(msg, flush=True)
        if self.log_callback:
            try:
                self.log_callback(msg)
            except Exception:
                pass

    def _write_log_line(self, log_path: Path, line: str) -> None:
        """Thread-safe write of a line to a log file."""
        if log_path is None:
            return
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_lock:
                with open(str(log_path), "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            pass

    # ── 核心运行方法 ──────────────────────────────────────

    def run(
        self,
        prompt: str,
        out_file: Path,
        *,
        add_dirs: Optional[List[Path]] = None,
        min_size_override: Optional[int] = None,
        extra_allowed_tools: Optional[List[str]] = None,
        stage_name: Optional[str] = None,
        output_validator: Optional[Callable[[str], str]] = None,
    ) -> bool:
        """
        调用 Claude CLI 执行 prompt，输出写入 out_file。

        Args:
            prompt: 完整提示词内容
            out_file: 输出文件路径
            add_dirs: 额外添加到 Claude 上下文中的目录
            min_size_override: 覆盖最小有效输出字节数
            extra_allowed_tools: 额外的允许工具
            stage_name: 阶段名称标签，用于日志文件命名

        Returns:
            True 成功, False 所有重试均失败
        """
        min_size = min_size_override if min_size_override is not None else self.min_output_size

        # 确保输出目录存在
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # 追加输出规则（防止 Claude 输出废话）
        full_prompt = prompt + (
            "\n\n---\n"
            "直接输出最终的文档正文。不要输出过程报告、统计摘要、文件清单或任何元描述。"
            "不要输出\"已完成\"\"执行完毕\"\"统计如下\"等总结语。"
            "输出从文档标题第一行直接开始。"
        )

        retry_feedback = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                ok, failure_reason = self._run_once(
                    full_prompt + retry_feedback, out_file, add_dirs, extra_allowed_tools,
                    min_size, attempt, stage_name=stage_name, output_validator=output_validator,
                )
                if ok:
                    return True
                if failure_reason:
                    retry_feedback = (
                        "\n\n---\nThe previous output failed final-document validation: "
                        f"{failure_reason}. Output only the required formal document. Do not explain."
                    )
            except Exception as e:
                self._log(f"    [ClaudeRunner] 异常: {e} (尝试 {attempt}/{self.max_retries})")
                if attempt < self.max_retries:
                    time.sleep(3 ** attempt)

        self._log(f"    [ClaudeRunner] 所有 {self.max_retries} 次重试均失败")
        return False

    def _run_once(
        self,
        prompt: str,
        out_file: Path,
        add_dirs: Optional[List[Path]],
        extra_tools: Optional[List[str]],
        min_size: int,
        attempt: int,
        stage_name: Optional[str] = None,
        output_validator: Optional[Callable[[str], str]] = None,
    ) -> Tuple[bool, str]:
        """执行单次 Claude 调用（Popen + 实时读取线程）。"""
        cmd = [self.claude_path, "-p", "--output-format", "text"]

        # 添加目录
        dirs_to_add: List[Path] = []
        if self.skills_dir and self.skills_dir.exists():
            dirs_to_add.append(self.skills_dir)
        if self.working_dir and self.working_dir.exists():
            dirs_to_add.append(self.working_dir)
        if add_dirs:
            dirs_to_add.extend(add_dirs)

        for d in dirs_to_add:
            if d.exists():
                cmd.extend(["--add-dir", str(d)])

        # 允许的工具
        tools = list(self.allowed_tools)
        if extra_tools:
            tools.extend(extra_tools)
        cmd.extend(["--allowedTools", ",".join(tools)])

        # ── 准备日志文件 ──
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = stage_name or f"stage_unknown"
        logs_dir = self._logs_dir
        stdout_log: Optional[Path] = None
        stderr_log: Optional[Path] = None
        pipeline_log: Optional[Path] = None

        if logs_dir:
            stdout_log = logs_dir / f"{timestamp}_{label}.log"
            stderr_log = logs_dir / f"{timestamp}_{label}_stderr.log"
            pipeline_log = logs_dir / "pipeline.log"

        # ── 启动进程 ──
        self._log(f"    [Claude] 启动: {' '.join(cmd[:4])} ... (尝试 {attempt}/{self.max_retries})")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line buffered
        )

        # Write prompt to stdin and close
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            self._log(f"    [Claude] stdin 写入失败: {e}")
            try:
                proc.kill()
            except Exception:
                pass
            return False, "could not write the prompt to the model process"

        # Collectors for full output (used for final validation)
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

        def read_stream(stream, log_path: Optional[Path], collector: List[str], prefix: str):
            """Read a stream line by line, write to log files, collect, and forward."""
            try:
                for line in iter(stream.readline, ""):
                    collector.append(line)
                    # Write to per-stage log file
                    if log_path:
                        self._write_log_line(log_path, line)
                    # Write to aggregated pipeline.log
                    if pipeline_log:
                        self._write_log_line(pipeline_log, f"{prefix}{line}")
                    # Forward via log callback (truncate long lines)
                    stripped = line.rstrip("\n\r")
                    if stripped:
                        display = stripped if len(stripped) <= 300 else stripped[:297] + "..."
                        self._log(f"    [Claude{prefix}] {display}")
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        # Start reader threads
        stdout_thread = threading.Thread(
            target=read_stream,
            args=(proc.stdout, stdout_log, stdout_lines, ""),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(proc.stderr, stderr_log, stderr_lines, "[STDERR] "),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        # ── Wait with timeout ──
        try:
            proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            self._log(f"    [Claude] 超时 ({self.timeout}s), 已终止进程 (尝试 {attempt}/{self.max_retries})")
            return False, "model process timed out"

        # Join reader threads (with timeout to avoid hanging)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        # ── Validate results ──
        if proc.returncode != 0:
            full_err = "".join(stderr_lines)
            err = full_err[:500] if full_err else "(无错误信息)"
            self._log(f"    Claude 退出码 {proc.returncode}: {err} (尝试 {attempt}/{self.max_retries})")
            # Write exit code to stderr log for diagnostics
            if stderr_log:
                self._write_log_line(stderr_log, f"\n--- Exit code: {proc.returncode} ---\n")
            return False, "model process exited with an error"

        output = "".join(stdout_lines).strip()
        if len(output) < min_size:
            self._log(f"    输出过小 ({len(output)} 字节 < {min_size}), 重试... (尝试 {attempt}/{self.max_retries})")
            return False, "output is too short"

        if output_validator:
            try:
                output = output_validator(output)
            except ValueError as exc:
                reason = str(exc) or "output does not meet the final-document contract"
                self._log(f"    Output validation failed: {reason} (attempt {attempt}/{self.max_retries})")
                return False, reason

        # Success — write output file
        out_file.write_text(output, encoding="utf-8")
        size = out_file.stat().st_size
        self._log(f"    [OK] {out_file.name}: {size} 字节")
        return True, ""

    # ── 便捷方法 ──────────────────────────────────────────

    def run_with_skill(
        self,
        skill_prompt: str,
        context: str,
        out_file: Path,
        *,
        add_dirs: Optional[List[Path]] = None,
        stage_name: Optional[str] = None,
    ) -> bool:
        """
        使用 Skill Prompt + 上下文数据 调用 Claude。

        Args:
            skill_prompt: 从 SKILL.md 加载的 skill 内容
            context: 注入的上下文数据（如解析后的文档内容）
            out_file: 输出文件路径
            add_dirs: 额外目录
            stage_name: 阶段名称标签，用于日志文件命名

        Returns:
            True 成功
        """
        full_prompt = f"""{skill_prompt}

---
## 上下文数据
{context}"""

        return self.run(full_prompt, out_file, add_dirs=add_dirs, stage_name=stage_name)

    def run_prompt(
        self,
        prompt: str,
        out_file: Path,
    ) -> bool:
        """最简单的调用方式：仅 prompt + 输出文件。"""
        return self.run(prompt, out_file)

    def __repr__(self) -> str:
        return f"ClaudeRunner(timeout={self.timeout}s, max_retries={self.max_retries})"
