"""Secure Sandbox Code Execution Engine with Docker container isolation and safe local fallback."""

import asyncio
import os
import shutil
import sys
import time
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None

from config.settings import settings
from judge.languages import LanguageConfig
from utils.logger import get_logger

logger = get_logger("SandboxJudge")


@dataclass
class ExecutionResult:
    status: str  # "OK", "TLE", "MLE", "RTE", "CE", "SECURITY_VIOLATION"
    stdout: str
    stderr: str
    execution_time: float  # In seconds
    memory_used_mb: float  # In MB
    exit_code: int

    @property
    def success(self) -> bool:
        return self.status == "OK" and self.exit_code == 0


class CodeSandbox:
    """Manages secure sandboxed compilation and execution of untrusted user code."""

    def __init__(
        self,
        timeout: int = 5,
        memory_limit_mb: int = 256,
        cpu_limit: float = 2.0,
        pids_limit: int = 64,
        image_name: str = "cp-sandbox:latest",
    ):
        self.timeout = timeout or settings.JUDGE_TIMEOUT
        self.memory_limit_mb = memory_limit_mb or settings.JUDGE_MEMORY_LIMIT
        self.cpu_limit = cpu_limit or settings.JUDGE_CPU_LIMIT
        self.pids_limit = pids_limit or settings.JUDGE_PIDS_LIMIT
        self.image_name = image_name or settings.DOCKER_SANDBOX_IMAGE
        self.docker_client = None
        self._check_docker()

    def _check_docker(self) -> None:
        """Attempts to initialize Docker client if Docker is installed and running."""
        if not settings.USE_DOCKER_SANDBOX:
            self.docker_client = None
            return

        try:
            import docker

            self.docker_client = docker.from_env()
            self.docker_client.ping()
            logger.info(
                "Docker daemon connected successfully. Container sandboxing active."
            )
        except Exception as e:
            logger.warning(
                f"Docker daemon not available ({e}). Fallback to local isolated process sandbox."
            )
            self.docker_client = None

    async def compile(self, work_dir: str, lang: LanguageConfig) -> tuple[bool, str]:
        """Compiles user code within the sandbox if the language is compiled."""
        if not lang.is_compiled or not lang.compile_cmd:
            return True, ""

        if self.docker_client:
            return await self._docker_compile(work_dir, lang)
        else:
            return await self._local_compile(work_dir, lang)

    async def compile_source(
        self,
        work_dir: str,
        lang: LanguageConfig,
        time_limit: float | None = None,
    ) -> ExecutionResult:
        """Compiles source and returns structured ExecutionResult."""
        if not lang.is_compiled or not lang.compile_cmd:
            return ExecutionResult(
                status="OK",
                stdout="",
                stderr="",
                execution_time=0.0,
                memory_used_mb=0.0,
                exit_code=0,
            )

        ok, logs = await self.compile(work_dir, lang)
        if ok:
            return ExecutionResult(
                status="OK",
                stdout=logs,
                stderr="",
                execution_time=0.0,
                memory_used_mb=0.0,
                exit_code=0,
            )
        else:
            return ExecutionResult(
                status="CE",
                stdout="",
                stderr=logs,
                execution_time=0.0,
                memory_used_mb=0.0,
                exit_code=1,
            )

    async def execute_test(
        self,
        work_dir: str,
        lang: LanguageConfig,
        stdin_input: str,
        time_limit: float | None = None,
    ) -> ExecutionResult:
        """Executes a single test case within the sandbox."""
        effective_timeout = (time_limit or self.timeout) * lang.time_multiplier

        if self.docker_client:
            return await self._docker_execute(
                work_dir, lang, stdin_input, effective_timeout
            )
        else:
            return await self._local_execute(
                work_dir, lang, stdin_input, effective_timeout
            )

    # =========================================================================
    # DOCKER SANDBOX IMPLEMENTATION
    # =========================================================================
    async def _docker_compile(
        self, work_dir: str, lang: LanguageConfig
    ) -> tuple[bool, str]:
        """Compiles code inside isolated container."""
        cmd_str = " ".join(lang.compile_cmd)
        container = None
        try:
            loop = asyncio.get_running_loop()
            container = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image=self.image_name,
                    command=f"/bin/sh -c 'cd /sandbox && {cmd_str}'",
                    volumes={work_dir: {"bind": "/sandbox", "mode": "rw"}},
                    network_mode="none",
                    mem_limit="512m",
                    pids_limit=128,
                    detach=True,
                    user="1000:1000",
                ),
            )
            result = await loop.run_in_executor(
                None, lambda: container.wait(timeout=30)
            )
            logs = await loop.run_in_executor(
                None,
                lambda: container.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                ),
            )

            status_code = result.get("StatusCode", 0)
            return (status_code == 0), logs
        except Exception as e:
            logger.error(f"Docker compilation error: {e}")
            return False, str(e)
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    async def _docker_execute(
        self,
        work_dir: str,
        lang: LanguageConfig,
        stdin_input: str,
        time_limit: float,
    ) -> ExecutionResult:
        """Runs the program in a locked-down, networkless Docker container."""
        input_path = os.path.join(work_dir, "input.in")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(stdin_input)

        run_cmd_str = " ".join(lang.run_cmd)
        exec_script = f"cd /sandbox && {run_cmd_str} < /sandbox/input.in"

        start_time = time.perf_counter()
        container = None
        try:
            loop = asyncio.get_running_loop()
            container = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image=self.image_name,
                    command=f"/bin/sh -c '{exec_script}'",
                    volumes={work_dir: {"bind": "/sandbox", "mode": "ro"}},
                    tmpfs={"/tmp": "size=64m,exec"},
                    network_mode="none",
                    mem_limit=f"{int(self.memory_limit_mb * lang.memory_multiplier)}m",
                    memswap_limit=f"{int(self.memory_limit_mb * lang.memory_multiplier)}m",
                    nano_cpus=int(self.cpu_limit * 1e9),
                    pids_limit=self.pids_limit,
                    read_only=True,
                    security_opt=["no-new-privileges:true"],
                    cap_drop=["ALL"],
                    user="1000:1000",
                    detach=True,
                ),
            )

            try:
                result = await loop.run_in_executor(
                    None, lambda: container.wait(timeout=int(time_limit) + 1)
                )
                elapsed = time.perf_counter() - start_time

                if elapsed > time_limit:
                    return ExecutionResult(
                        "TLE", "", "Time limit exceeded", elapsed, 0.0, -1
                    )

                logs_stdout = await loop.run_in_executor(
                    None,
                    lambda: container.logs(stdout=True, stderr=False).decode(
                        "utf-8", errors="replace"
                    ),
                )
                logs_stderr = await loop.run_in_executor(
                    None,
                    lambda: container.logs(stdout=False, stderr=True).decode(
                        "utf-8", errors="replace"
                    ),
                )

                exit_code = result.get("StatusCode", 0)
                if exit_code != 0:
                    if exit_code == 137:
                        return ExecutionResult(
                            "MLE",
                            logs_stdout,
                            "Memory Limit Exceeded",
                            elapsed,
                            self.memory_limit_mb,
                            exit_code,
                        )
                    return ExecutionResult(
                        "RTE", logs_stdout, logs_stderr, elapsed, 32.0, exit_code
                    )

                return ExecutionResult(
                    "OK", logs_stdout, logs_stderr, elapsed, 32.0, exit_code
                )

            except Exception:
                elapsed = time.perf_counter() - start_time
                return ExecutionResult(
                    "TLE", "", "Time limit exceeded", elapsed, 0.0, -1
                )

        except Exception as e:
            logger.error(f"Docker execution error: {e}")
            return ExecutionResult("RTE", "", str(e), 0.0, 0.0, 1)
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    # =========================================================================
    # LOCAL ISOLATED PROCESS SANDBOX FALLBACK (WINDOWS & LINUX SUPPORT)
    # =========================================================================
    async def _local_compile(
        self, work_dir: str, lang: LanguageConfig
    ) -> tuple[bool, str]:
        """Local subprocess compilation in isolated directory."""
        if not lang.compile_cmd:
            return True, ""

        compile_cmd = list(lang.compile_cmd)
        # Ưu tiên sử dụng toolchain C/C++ tích hợp trực tiếp trong dự án
        if compile_cmd and compile_cmd[0] in ("g++", "gcc"):
            bundled_compiler = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                "cpp_core", "compiler", "w64devkit", "bin", f"{compile_cmd[0]}.exe"
            )
            if os.path.exists(bundled_compiler):
                compile_cmd[0] = bundled_compiler

        try:
            proc = await asyncio.create_subprocess_exec(
                *compile_cmd,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            log_output = stderr.decode("utf-8", errors="replace") or stdout.decode(
                "utf-8", errors="replace"
            )
            return (proc.returncode == 0), log_output
        except FileNotFoundError:
            return (
                False,
                f"Compiler for {lang.name} ('{compile_cmd[0]}') not found on host machine.",
            )
        except Exception as e:
            return False, str(e)

    async def _local_execute(
        self,
        work_dir: str,
        lang: LanguageConfig,
        stdin_input: str,
        time_limit: float,
    ) -> ExecutionResult:
        safe_env = dict(os.environ)
        safe_env["LANG"] = "C.UTF-8"
        safe_env["LC_ALL"] = "C.UTF-8"

        # Adapt run_cmd for host environment if needed
        run_cmd = list(lang.run_cmd)
        if (
            run_cmd
            and run_cmd[0] in ("python3", "python", "py")
            or lang.id.startswith("python")
        ):
            run_cmd[0] = sys.executable
        elif run_cmd and run_cmd[0] in ("pypy3", "pypy"):
            # Nếu chưa cài PyPy riêng trên host, fallback sang CPython hiện hành
            if not shutil.which(run_cmd[0]):
                run_cmd[0] = sys.executable
        elif run_cmd and (run_cmd[0] in ("node", "nodejs") or lang.id.startswith("js")):
            # Ưu tiên sử dụng Node.js tích hợp trực tiếp trong dự án
            bundled_node = os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                "bin", "node", "node.exe"
            )
            if os.path.exists(bundled_node):
                run_cmd[0] = bundled_node
        elif run_cmd and run_cmd[0].startswith("./"):
            bin_name = run_cmd[0][2:]
            exe_candidate = os.path.join(work_dir, f"{bin_name}.exe")
            bin_candidate = os.path.join(work_dir, bin_name)
            if os.path.exists(exe_candidate):
                run_cmd[0] = exe_candidate
            elif os.path.exists(bin_candidate):
                run_cmd[0] = bin_candidate

        start_time = time.perf_counter()
        peak_memory_mb = 0.0

        try:
            proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                cwd=work_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=stdin_input.encode("utf-8")),
                    timeout=time_limit,
                )
                elapsed = time.perf_counter() - start_time

                stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                stderr_str = stderr_bytes.decode("utf-8", errors="replace")

                if proc.returncode != 0:
                    return ExecutionResult(
                        "RTE",
                        stdout_str,
                        stderr_str,
                        elapsed,
                        peak_memory_mb,
                        proc.returncode,
                    )

                return ExecutionResult(
                    "OK", stdout_str, stderr_str, elapsed, peak_memory_mb, 0
                )

            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                elapsed = time.perf_counter() - start_time
                return ExecutionResult(
                    "TLE", "", "Time limit exceeded", elapsed, peak_memory_mb, -1
                )

        except FileNotFoundError:
            return ExecutionResult(
                "RTE",
                "",
                f"Runtime for {lang.name} ('{run_cmd[0]}') not found.",
                0.0,
                0.0,
                1,
            )
        except Exception as e:
            return ExecutionResult("RTE", "", str(e), 0.0, 0.0, 1)
