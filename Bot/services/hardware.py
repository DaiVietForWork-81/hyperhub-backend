"""
services/hardware.py
Phát hiện phần cứng máy chủ (CPU / RAM / GPU / Disk) và gợi ý cấu hình Ollama tối ưu.

- Không phụ thuộc torch (dùng psutil + nvidia-smi + platform, graceful fallback).
- Dùng bởi AI Core: báo cáo `/ai_status`, nhánh "phần cứng", auto-tune num_ctx.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("Hardware")

try:
    import psutil

    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False


def _fmt_gb(byte_count: float) -> str:
    return f"{byte_count / (1024 ** 3):.1f} GB"


def get_cpu_info() -> dict[str, Any]:
    """Thông tin CPU (hỗ trợ đọc chuẩn trên cả Windows và Linux /proc/cpuinfo)."""
    model_name = platform.processor() or platform.machine()
    # Trên Linux, platform.processor() thường rỗng hoặc chỉ là x86_64, đọc /proc/cpuinfo để lấy model thực
    if platform.system() == "Linux" and os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("model name"):
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[1].strip():
                            model_name = parts[1].strip()
                            break
        except Exception as e:
            logger.debug(f"Linux /proc/cpuinfo read error: {e}")

    info: dict[str, Any] = {
        "model": model_name,
        "arch": platform.machine(),
        "physical_cores": None,
        "logical_cores": os.cpu_count() or 1,
        "usage_percent": None,
    }
    if HAS_PSUTIL:
        try:
            info["physical_cores"] = psutil.cpu_count(logical=False)
            info["logical_cores"] = psutil.cpu_count(logical=True) or info["logical_cores"]
            info["usage_percent"] = psutil.cpu_percent(interval=None)
        except Exception as e:
            logger.debug(f"CPU detect error: {e}")
    return info


def get_ram_info() -> dict[str, Any]:
    """Thông tin RAM (total / free / usage), có fallback /proc/meminfo trên Linux."""
    info: dict[str, Any] = {"total_gb": None, "free_gb": None, "usage_percent": None}
    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            info["total_gb"] = round(mem.total / (1024 ** 3), 1)
            info["free_gb"] = round(mem.available / (1024 ** 3), 1)
            info["usage_percent"] = mem.percent
        except Exception as e:
            logger.debug(f"RAM detect error: {e}")

    # Fallback cho Linux nếu psutil chưa cài đặt hoặc thiếu trường
    if platform.system() == "Linux" and os.path.exists("/proc/meminfo") and info["total_gb"] is None:
        try:
            mem_dict = {}
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val_str = parts[1].strip().split()[0]
                        if val_str.isdigit():
                            mem_dict[key] = int(val_str)
            if "MemTotal" in mem_dict:
                total = mem_dict["MemTotal"] * 1024
                available = mem_dict.get("MemAvailable", mem_dict.get("MemFree", 0)) * 1024
                info["total_gb"] = round(total / (1024 ** 3), 1)
                info["free_gb"] = round(available / (1024 ** 3), 1)
                info["usage_percent"] = round(100 * (total - available) / total, 1)
        except Exception as e:
            logger.debug(f"RAM /proc/meminfo fallback error: {e}")
    return info


_gpu_info_cache: list[dict[str, Any]] | None = None
_gpu_last_checked_time: float = 0.0
_GPU_CACHE_TTL: float = 3.0  # Bộ đệm 3 giây tránh gọi nvidia-smi subprocess dồn dập
_HARDWARE_CACHE_FILE = Path("data/hardware_cache.json")


def get_gpu_info(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Danh sách GPU (nvidia-smi -> torch -> rỗng), có bộ đệm bộ nhớ TTL 3s và file cache."""
    global _gpu_info_cache, _gpu_last_checked_time
    import time

    now = time.time()
    if not force_refresh:
        if _gpu_info_cache is not None and (now - _gpu_last_checked_time) < _GPU_CACHE_TTL:
            return _gpu_info_cache
        if _gpu_info_cache is None and _HARDWARE_CACHE_FILE.exists():
            try:
                import json
                with open(_HARDWARE_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, list):
                        _gpu_info_cache = cached_data
                        _gpu_last_checked_time = now
                        return cached_data
            except Exception as e:
                logger.debug(f"Không thể đọc hardware_cache.json: {e}")

    gpus_res = _detect_gpu_info_internal()
    _gpu_info_cache = gpus_res
    _gpu_last_checked_time = now
    try:
        import json
        _HARDWARE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HARDWARE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(gpus_res, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"Không thể ghi hardware_cache.json: {e}")
    return gpus_res


def _detect_gpu_info_internal() -> list[dict[str, Any]]:
    """Hàm dò tìm thông số GPU thực tế."""
    # 1. nvidia-smi (không cần torch)
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            gpus = []
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append({
                        "name": parts[0],
                        "vendor": "nvidia",
                        "vram_total_gb": round(float(parts[1]) / 1024, 1),
                        "vram_free_gb": round(float(parts[2]) / 1024, 1),
                        "usage_percent": float(parts[3]),
                        "backend": "nvidia-smi",
                    })
            if gpus:
                return gpus
    except Exception as e:
        logger.debug(f"nvidia-smi detect error: {e}")

    # 2. rocm-smi (cho AMD GPU trên Linux có cài ROCm)
    try:
        out = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--showproductname", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            import json
            raw_data = json.loads(out.stdout.strip())
            gpus = []
            for card_id, card_info in raw_data.items():
                if not isinstance(card_info, dict):
                    continue
                name = card_info.get("Card series") or card_info.get("Product Name") or f"AMD Radeon ({card_id})"
                vram_bytes = card_info.get("VRAM Total Memory (B)") or 0
                vram_used_bytes = card_info.get("VRAM Total Used Memory (B)") or 0
                vram_gb = round(float(vram_bytes) / (1024 ** 3), 1) if vram_bytes else None
                free_gb = round((float(vram_bytes) - float(vram_used_bytes)) / (1024 ** 3), 1) if vram_bytes else None
                gpus.append({
                    "name": name,
                    "vendor": "amd",
                    "vram_total_gb": vram_gb,
                    "vram_free_gb": free_gb,
                    "usage_percent": None,
                    "backend": "rocm-smi",
                })
            if gpus:
                return gpus
    except Exception as e:
        logger.debug(f"rocm-smi detect error: {e}")

    # 3. torch (nếu đã cài)
    try:
        import torch

        if torch.cuda.is_available():
            gpus = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpus.append({
                    "name": props.name,
                    "vendor": _infer_vendor(props.name),
                    "vram_total_gb": round(props.total_memory / (1024 ** 3), 1),
                    "vram_free_gb": None,
                    "usage_percent": None,
                    "backend": "torch",
                })
            if gpus:
                return gpus
    except Exception as e:
        logger.debug(f"torch GPU detect error: {e}")

    # 3. Windows WMI (hỗ trợ phát hiện AMD Radeon, Intel HD/Iris, NVIDIA khi không có nvidia-smi)
    if platform.system() == "Windows":
        try:
            import json
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                raw = json.loads(out.stdout.strip())
                items = [raw] if isinstance(raw, dict) else raw
                gpus = []
                for item in items:
                    name = item.get("Name")
                    if not name:
                        continue
                    vram_bytes = item.get("AdapterRAM") or 0
                    vram_gb = round(vram_bytes / (1024 ** 3), 1) if vram_bytes > 0 else None
                    gpus.append({
                        "name": name,
                        "vendor": _infer_vendor(name),
                        "vram_total_gb": vram_gb,
                        "vram_free_gb": None,
                        "usage_percent": None,
                        "backend": "wmi",
                    })
                if gpus:
                    return gpus
        except Exception as e:
            logger.debug(f"WMI GPU detect error: {e}")

    # 4. Linux lspci (phát hiện GPU Intel, AMD, NVIDIA trên Ubuntu/Linux khi không có nvidia-smi)
    if platform.system() == "Linux":
        try:
            out = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0 and out.stdout.strip():
                gpus = []
                for line in out.stdout.strip().splitlines():
                    lower_line = line.lower()
                    if any(tag in lower_line for tag in ["vga compatible controller", "3d controller", "display controller"]):
                        # Trích xuất tên card đồ họa từ chuỗi output của lspci
                        parts = line.split(":", 2)
                        name = parts[-1].strip() if len(parts) >= 3 else line
                        gpus.append({
                            "name": name,
                            "vendor": _infer_vendor(name),
                            "vram_total_gb": None,
                            "vram_free_gb": None,
                            "usage_percent": None,
                            "backend": "lspci",
                        })
                if gpus:
                    return gpus
        except Exception as e:
            logger.debug(f"Linux lspci GPU detect error: {e}")

    return []


def _infer_vendor(gpu_name: str) -> str:
    """Đoán hãng GPU từ tên (dùng khi không có nvidia-smi)."""
    name = (gpu_name or "").upper()
    if "NVIDIA" in name or "GEFORCE" in name or "QUADRO" in name or "TESLA" in name:
        return "nvidia"
    if "AMD" in name or "RADEON" in name:
        return "amd"
    if "INTEL" in name:
        return "intel"
    if "APPLE" in name or " METAL" in name:
        return "apple"
    return "unknown"


def get_disk_info(path: str | Path | None = None) -> dict[str, Any]:
    """Dung lượng ổ đĩa chứa project."""
    target = Path(path) if path else Path(__file__).resolve().parent.parent
    try:
        usage = shutil.disk_usage(str(target))
        return {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "usage_percent": round(100 * (usage.total - usage.free) / usage.total, 1),
        }
    except Exception as e:
        logger.debug(f"Disk detect error: {e}")
        return {"total_gb": None, "free_gb": None, "usage_percent": None}


def get_project_cache_info() -> dict[str, Any]:
    """Thông tin bộ đệm và bộ nhớ ảo nội bộ khép kín của dự án (data/cache/)."""
    cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache"
    total_bytes = 0
    file_count = 0
    if cache_dir.exists():
        try:
            for p in cache_dir.rglob("*"):
                if p.is_file():
                    total_bytes += p.stat().st_size
                    file_count += 1
        except Exception:
            pass

    max_mb = 1024
    total_mb = round(total_bytes / (1024 * 1024), 2)
    return {
        "cache_dir": str(cache_dir),
        "total_mb": total_mb,
        "max_mb": max_mb,
        "file_count": file_count,
        "usage_percent": round(100 * total_mb / max_mb, 1),
        "is_self_contained": True,
    }


def get_hardware_info() -> dict[str, Any]:
    """Tổng hợp toàn bộ phần cứng và bộ đệm dự án."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": get_cpu_info(),
        "ram": get_ram_info(),
        "gpus": get_gpu_info(),
        "disk": get_disk_info(),
        "project_cache": get_project_cache_info(),
        "ollama_gpu": get_ollama_gpu_status(),
    }


def get_ollama_gpu_status(
    base_url: str = "http://localhost:11434", timeout: float = 0.5
) -> dict[str, Any]:
    """Hỏi Ollama (/api/ps) xem model đang offload bao nhiêu % lên GPU.

    Ground truth theo tài liệu Ollama: PROCESSOR 100% GPU / 100% CPU / chia đôi.
    """
    import json
    import urllib.request

    status: dict[str, Any] = {"loaded": [], "summary": "Ollama chưa nạp model nào"}
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/ps")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
        loaded = []
        for m in data.get("models", []):
            size = m.get("size", 0) or 0
            vram = m.get("size_vram", 0) or 0
            pct = round(vram / size * 100) if size else 0
            if pct >= 99:
                proc = "100% GPU"
            elif pct <= 0:
                proc = "100% CPU"
            else:
                proc = f"{100 - pct:.0f}%/{pct:.0f}% CPU/GPU"
            loaded.append({
                "name": m.get("name", "?"),
                "size_gb": round(size / (1024 ** 3), 2),
                "vram_gb": round(vram / (1024 ** 3), 2),
                "offload_percent": pct,
                "processor": proc,
            })
        status["loaded"] = loaded
        if loaded:
            status["summary"] = "; ".join(
                f"{m['name']}: {m['processor']}" for m in loaded
            )
    except Exception as e:
        status["summary"] = f"Không kết nối được Ollama ({e})"
    return status


def classify_system(hw: dict[str, Any] | None = None) -> dict[str, str]:
    """Phân loại hệ thống để chọn profile tối ưu Ollama.

    - nvidia_full: card NVIDIA VRAM >= 6GB -> ép full GPU + ctx lớn
    - nvidia_hybrid: card NVIDIA VRAM < 6GB -> để Ollama tự chia CPU/GPU
    - amd_hybrid: card AMD Radeon -> để Ollama tự chia CPU/GPU + đa luồng
    - intel_igpu: card Intel -> để Ollama chia sẻ CPU/GPU
    - auto: còn lại -> auto + ctx theo RAM
    """
    hw = hw or {"gpus": get_gpu_info(), "ram": get_ram_info()}
    gpus = hw.get("gpus", []) or []
    nvidia_cards = [g for g in gpus if g.get("vendor") == "nvidia" and (g.get("vram_total_gb") or 0) > 0]

    if nvidia_cards:
        best = max(nvidia_cards, key=lambda g: g.get("vram_total_gb") or 0)
        vram = best.get("vram_total_gb") or 0
        if vram >= 6:
            return {
                "profile": "nvidia_full",
                "label": "🚀 NVIDIA Full GPU",
                "reason": f"{best.get('name', 'NVIDIA')} VRAM {vram} GB: đủ chứa model 4B + KV-cache -> ép full offload",
            }
        return {
            "profile": "nvidia_hybrid",
            "label": "⚖️ NVIDIA Hybrid",
            "reason": f"{best.get('name', 'NVIDIA')} VRAM {vram} GB < 6GB: để Ollama tự chia CPU/GPU",
        }

    amd_cards = [g for g in gpus if g.get("vendor") == "amd" and (g.get("vram_total_gb") or 0) > 0]
    if amd_cards:
        best = max(amd_cards, key=lambda g: g.get("vram_total_gb") or 0)
        vram = best.get("vram_total_gb") or 0
        if vram >= 6:
            return {
                "profile": "amd_full",
                "label": f"🚀 AMD Radeon ROCm ({best.get('name')})",
                "reason": f"{best.get('name')} VRAM {vram} GB: đủ chứa model 4B + KV-cache -> ép full offload ROCm",
            }
        elif vram <= 2:
            return {
                "profile": "amd_legacy",
                "label": f"⚠️ AMD Legacy GPU ({best.get('name')})",
                "reason": f"{best.get('name')} VRAM {vram} GB <= 2GB: tự động fallback sang CPU an toàn để tránh lỗi rác token",
            }
        return {
            "profile": "amd_hybrid",
            "label": f"🎮 AMD GPU ({best.get('name')})",
            "reason": f"{best.get('name')} VRAM {vram} GB: Ollama tự phân bổ GPU & CPU ({os.cpu_count() or 4} threads)",
        }

    intel_cards = [g for g in gpus if g.get("vendor") == "intel" and (g.get("vram_total_gb") or 0) > 0]
    if intel_cards:
        best = max(intel_cards, key=lambda g: g.get("vram_total_gb") or 0)
        vram = best.get("vram_total_gb") or 0
        return {
            "profile": "intel_igpu",
            "label": f"🖥️ Intel Graphics ({best.get('name')})",
            "reason": f"{best.get('name')} VRAM {vram} GB: Ollama kết hợp GPU/CPU ({os.cpu_count() or 4} threads)",
        }

    return {
        "profile": "auto",
        "label": "🖥️ Auto (CPU/Vulkan iGPU)",
        "reason": "Không phát hiện card NVIDIA/AMD: để Ollama tự quyết offload, ctx theo RAM trống",
    }


def recommend_llm_options(hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gợi ý options Ollama theo TỪNG HỆ THỐNG (VRAM + RAM trống + CPU threads).

    Trả về: {"num_ctx", "num_gpu" (None = auto), "num_thread", "profile", "label", "reason"}.
    Truyền hw vào để test được mà không cần đọc phần cứng thật.
    """
    live_hw = hw or {"gpus": get_gpu_info(), "ram": get_ram_info()}
    cls = classify_system(live_hw)
    ram = live_hw.get("ram", {}) or {}
    free_gb = ram.get("free_gb")

    # num_ctx theo RAM trống (áp dụng mọi profile, lấy min với giới hạn VRAM bên dưới)
    if free_gb is None:
        num_ctx = 3072
    elif free_gb >= 8:
        num_ctx = 8192
    elif free_gb >= 4:
        num_ctx = 4096
    elif free_gb < 2:
        num_ctx = 2048
    else:
        num_ctx = 3072

    num_gpu: int | None = None
    if cls["profile"] in ("nvidia_full", "amd_full"):
        num_gpu = 999  # ép full offload: VRAM đủ chứa model 4B (~2.8GB) + KV-cache 8k (~1.2GB)
        if (free_gb or 0) < 4:
            num_ctx = min(num_ctx, 4096)
    elif cls["profile"] == "amd_legacy":
        num_gpu = 0  # Ép thuần CPU để tránh lỗi rác ký tự / corrupt matrix trên GPU AMD cũ
        num_ctx = min(num_ctx, 2048)
    elif cls["profile"] == "nvidia_hybrid":
        num_ctx = min(num_ctx, 4096)  # VRAM nhỏ: giữ ctx vừa để KV-cache không tràn
    elif cls["profile"] in ("amd_hybrid", "intel_igpu"):
        num_ctx = min(num_ctx, 4096)

    # Tối ưu hóa cho C++ SIMD inference (llama.cpp): Ưu tiên physical cores để tránh cache contention
    try:
        import psutil
        num_thread = psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except Exception:
        num_thread = os.cpu_count() or 4

    return {
        "num_ctx": num_ctx,
        "num_gpu": num_gpu,
        "num_thread": num_thread,
        "profile": cls["profile"],
        "label": cls["label"],
        "reason": cls["reason"],
    }


def format_hardware_report(hw: dict[str, Any] | None = None) -> str:
    """Render báo cáo phần cứng thành text (dùng cho Discord embed)."""
    hw = hw or get_hardware_info()
    cpu = hw.get("cpu", {})
    ram = hw.get("ram", {})
    gpus = hw.get("gpus", [])
    disk = hw.get("disk", {})

    def _g(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "N/A"

    cpu_load = ""
    if cpu.get("usage_percent") is not None:
        cpu_load = f" • load {cpu.get('usage_percent')}%"
    ram_used = ""
    if ram.get("usage_percent") is not None:
        ram_used = f" (dùng {ram.get('usage_percent')}%)"

    lines = [
        f"🖥️ **OS:** {hw.get('os', 'N/A')}",
        f"• 🧠 **CPU:** {cpu.get('model') or 'N/A'} "
        f"({_g(cpu.get('physical_cores'))}P/{_g(cpu.get('logical_cores'))}T{cpu_load})",
        f"• 💾 **RAM:** {_g(ram.get('free_gb'), ' GB free')} / "
        f"{_g(ram.get('total_gb'), ' GB total')}{ram_used}",
    ]
    if gpus:
        for i, g in enumerate(gpus, 1):
            if g.get("vram_free_gb") is not None:
                vram = f"{g['vram_free_gb']} GB free / {_g(g.get('vram_total_gb'), ' GB')}"
            elif g.get("vram_total_gb") is not None:
                vram = f"{g['vram_total_gb']} GB"
            else:
                vram = "N/A"
            lines.append(f"• 🎮 **GPU {i}:** {g.get('name', 'N/A')} (VRAM {vram})")
    else:
        lines.append("• 🎮 **GPU:** Không phát hiện card rời (Ollama dùng CPU/Vulkan iGPU)")

    ollama_gpu = hw.get("ollama_gpu") or {}
    if ollama_gpu.get("loaded"):
        for m in ollama_gpu["loaded"]:
            lines.append(
                f"• ⚡ **Ollama `{m['name']}`:** {m['processor']} "
                f"({m['vram_gb']}/{m['size_gb']} GB trên VRAM)"
            )
    else:
        lines.append(f"• ⚡ **Ollama GPU:** {ollama_gpu.get('summary', 'N/A')}")
    lines.append(
        f"• 💽 **Disk:** {_g(disk.get('free_gb'), ' GB free')} / {_g(disk.get('total_gb'), ' GB total')}"
    )

    rec = recommend_llm_options(hw)
    gpu_mode = "ép full GPU (`num_gpu=999`)" if rec.get("num_gpu") else "auto (Ollama tự chia)"
    lines.append(f"\n⚙️ **Profile:** {rec.get('label', '')}")
    lines.append(f"• Lý do: {rec.get('reason', '')}")
    lines.append(
        f"• **Ollama auto-tune:** `num_ctx={rec['num_ctx']}`, GPU {gpu_mode}"
    )
    return "\n".join(lines)
