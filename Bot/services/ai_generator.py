"""
services/ai_generator.py
Local AI Problem Generator & Extractor using Qwen3-4B-Instruct-2507 via Ollama for Ranked 1:1 Competitive Programming.
Models are stored directly inside the project's 'models/' folder (0 MB on drive C:).
Supports automatic prompt engineering, raw text parsing/extraction, JSON parsing, testcase generation, and sandbox code validation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from config.settings import (
    settings,
    AI_MODEL_NAME,
    AI_BACKUP_MODEL_NAME,
    AI_VERIFIER_MODEL_NAME,
)
from services.problem_types import DuelProblem
from services.rank import get_tier_division

# Tá»± Ä‘á»™ng gÃ¡n thÆ° má»¥c lÆ°u trá»¯ Model AI vÃ o trá»±c tiáº¿p trong project (models/)
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["OLLAMA_MODELS"] = MODELS_DIR

logger = logging.getLogger("AIGenerator")


def _gpu_option() -> dict[str, Any]:
    """Tráº£ vá» {'num_gpu': N} theo cáº¥u hÃ¬nh vÃ  hardware profile an toÃ n."""
    try:
        from services.hardware import recommend_llm_options
        hw = recommend_llm_options()
        hw_num_gpu = hw.get("num_gpu")
    except Exception:
        hw_num_gpu = 0

    env_num_gpu = getattr(settings, "OLLAMA_NUM_GPU", None)
    if env_num_gpu is not None:
        num_gpu = int(env_num_gpu)
    elif hw_num_gpu is not None:
        num_gpu = int(hw_num_gpu)
    else:
        num_gpu = 0
    return {"num_gpu": num_gpu}

TIER_GUIDELINES: dict[str, dict[str, Any]] = {
    "T8": {
        "division": "Div. 4",
        "rating": "300 pts",
        "time": 15,
        "kb": 64,
        "topics": "Xá»­ lÃ½ máº£ng 1D Ä‘Æ¡n giáº£n, Ä‘áº¿m pháº§n tá»­ cháºµn/láº», tÃ­nh tá»•ng theo Ä‘iá»u kiá»‡n, xá»­ lÃ½ chuá»—i cÆ¡ báº£n, phÃ©p toÃ¡n sá»‘ há»c.",
        "constraints": "N <= 1000, A[i] <= 10^6",
        "time_complexity": "O(N) hoáº·c O(N log N)",
    },
    "T7": {
        "division": "Div. 4",
        "rating": "550 pts",
        "time": 15,
        "kb": 64,
        "topics": "Máº£ng tiá»n tá»‘ (Prefix Sum 1D), SÃ ng sá»‘ nguyÃªn tá»‘ Eratosthenes, Ä‘áº¿m táº§n sá»‘ kÃ½ tá»± (Hash map/array), sáº¯p xáº¿p cÆ¡ báº£n.",
        "constraints": "N <= 10^5, A[i] <= 10^9",
        "time_complexity": "O(N) hoáº·c O(N log N)",
    },
    "T6": {
        "division": "Div. 4",
        "rating": "850 pts",
        "time": 18,
        "kb": 64,
        "topics": "Thuáº­t toÃ¡n tham lam (Greedy), thuáº­t toÃ¡n Kadane tÃ¬m Ä‘oáº¡n con lá»›n nháº¥t, Cá»­a sá»• trÆ°á»£t cÆ¡ báº£n (Sliding Window).",
        "constraints": "N <= 2 * 10^5, -10^9 <= A[i] <= 10^9",
        "time_complexity": "O(N) hoáº·c O(N log N)",
    },
    "T5": {
        "division": "Div. 3",
        "rating": "1300 pts",
        "time": 20,
        "kb": 128,
        "topics": "Cháº·t nhá»‹ phÃ¢n káº¿t quáº£ (Binary Search on Answer), Hai con trá» Ä‘iá»u kiá»‡n phá»©c táº¡p (Two Pointers with conditions), NÃ©n tá»a Ä‘á»™, Máº£ng hiá»‡u.",
        "constraints": "N <= 2 * 10^5, 1 <= K <= 10^9",
        "time_complexity": "O(N log(Ans)) hoáº·c O(N log N)",
    },
    "T4": {
        "division": "Div. 3",
        "rating": "1500 pts",
        "time": 22,
        "kb": 128,
        "topics": "Quy hoáº¡ch Ä‘á»™ng 0/1 Knapsack tá»‘i Æ°u giÃ¡ trá»‹ & truy váº¿t, BFS Ä‘a nguá»“n (Multi-source BFS), DFS chu trÃ¬nh vÃ  liÃªn thÃ´ng, DP máº£ng con.",
        "constraints": "N <= 1000, W <= 10^4 hoáº·c N, M <= 10^5",
        "time_complexity": "O(N * W) hoáº·c O(N + M)",
    },
    "T3": {
        "division": "Div. 3",
        "rating": "1750 pts",
        "time": 25,
        "kb": 128,
        "topics": "Quy hoáº¡ch Ä‘á»™ng 2D Grid DP cÃ³ váº­t cáº£n & modulo 10^9+7, Sáº¯p xáº¿p Topo thá»© tá»± tá»« Ä‘iá»ƒn nhá» nháº¥t (Kahn + min-heap), Kruskal MST cÃ³ Ä‘iá»u kiá»‡n, LIS O(N log N).",
        "constraints": "N, M <= 2 * 10^5 hoáº·c N, M <= 1000 (Grid DP)",
        "time_complexity": "O(N * M) hoáº·c O((N + M) log N)",
    },
    "LT2": {
        "division": "Div. 2",
        "rating": "2000 pts",
        "time": 30,
        "kb": 256,
        "topics": "CÃ¢y phÃ¢n Ä‘oáº¡n vá»›i Lazy Propagation (Segment Tree Range Update & Query), Binary Lifting tÃ¬m LCA, CÃ¢y Fenwick 2D.",
        "constraints": "N, Q <= 2 * 10^5",
        "time_complexity": "O((N + Q) log N)",
    },
    "MT2": {
        "division": "Div. 2",
        "rating": "2200 pts",
        "time": 35,
        "kb": 256,
        "topics": "Dijkstra trÃªn khÃ´ng gian tráº¡ng thÃ¡i (State-space Dijkstra vá»›i K láº§n Æ°u tiÃªn cáº¡nh), Cáº§u vÃ  Khá»›p (Tarjan Bridge & Articulation points), Digit DP.",
        "constraints": "N <= 10^5, M <= 2 * 10^5, K <= 10",
        "time_complexity": "O(K * M log(K * N)) hoáº·c O(N + M)",
    },
    "HT2": {
        "division": "Div. 2",
        "rating": "2350 pts",
        "time": 40,
        "kb": 256,
        "topics": "Rerooting Tree DP (All-roots DP), Heavy-Light Decomposition (HLD) cáº­p nháº­t Ä‘Æ°á»ng Ä‘i cÃ¢y, Segment Tree Beats, 2-SAT.",
        "constraints": "N, Q <= 2 * 10^5",
        "time_complexity": "O(N log N) hoáº·c O((N + Q) log^2 N)",
    },
    "LT1": {
        "division": "Div. 1",
        "rating": "2500 pts",
        "time": 45,
        "kb": 512,
        "topics": "MÃ´ hÃ¬nh hÃ³a Luá»“ng cá»±c Ä‘áº¡i / LÃ¡t cáº¯t háº¹p nháº¥t (Min-Cut Project Selection Problem), Persistent Segment Tree, Min-Cost Max-Flow.",
        "constraints": "N <= 1000, M <= 10000",
        "time_complexity": "O(V^2 * E) hoáº·c O(Q log N)",
    },
    "MT1": {
        "division": "Div. 1",
        "rating": "2800 pts",
        "time": 50,
        "kb": 512,
        "topics": "PhÃ¢n rÃ£ trá»ng tÃ¢m cÃ¢y (Centroid Decomposition), Link-Cut Tree (LCT), CÃ¢y Palindrome (EerTree), Biáº¿n Ä‘á»•i Fourier nhanh (FFT / NTT).",
        "constraints": "N <= 10^5, K <= N",
        "time_complexity": "O(N log^2 N) hoáº·c O(N log N)",
    },
    "HT1": {
        "division": "Div. 1",
        "rating": "3000 pts",
        "time": 60,
        "kb": 512,
        "topics": "LÅ©y thá»«a ma tráº­n trÃªn Semi-ring (min, +) tÃ¬m Ä‘Æ°á»ng Ä‘i Ä‘Ãºng K bÆ°á»›c, Suffix Automaton vá»›i liÃªn káº¿t cÃ¢y cha, Matroid Intersection.",
        "constraints": "N <= 100, K <= 10^18",
        "time_complexity": "O(N^3 log K)",
    },
}

DEFAULT_THEMES = [
    "ngÃ¢n hÃ ng & giao dá»‹ch tÃ i chÃ­nh",
    "sÃ n chá»©ng khoÃ¡n & HFT",
    "chuá»—i cung á»©ng & tá»‘i Æ°u logistics",
    "há»‡ thá»‘ng giao thÃ´ng thÃ´ng minh & phÃ¢n luá»“ng",
    "thÆ°Æ¡ng máº¡i Ä‘iá»‡n tá»­ & flash sale",
    "trung tÃ¢m dá»¯ liá»‡u & cÃ¢n báº±ng táº£i mÃ¡y chá»§",
    "máº¡ng xÃ£ há»™i & lan truyá»n thÃ´ng tin",
    "y táº¿ & Ä‘iá»u phá»‘i cáº¥p cá»©u kháº©n cáº¥p",
    "game online & xáº¿p háº¡ng Ä‘áº¥u trÆ°á»ng",
    "lÆ°á»›i Ä‘iá»‡n thÃ´ng minh & tá»‘i Æ°u nÄƒng lÆ°á»£ng",
]


def validate_python_solution(
    solution_code: str,
    sample_input: str,
    sample_output: str,
    secret_tests: list[dict[str, str]],
    timeout_sec: float = 3.0,
) -> tuple[bool, str]:
    """Cháº¡y thá»­ nghiá»‡m code giáº£i báº±ng Python trong sandbox mini."""
    if not solution_code or not solution_code.strip():
        return False, "Code giáº£i rá»—ng!"

    all_tests = [{"input": sample_input, "output": sample_output}] + secret_tests

    for idx, test in enumerate(all_tests):
        t_in = str(test.get("input", "")).strip()
        t_out = str(test.get("output", "")).strip()

        try:
            proc = subprocess.run(
                [sys.executable, "-c", solution_code],
                input=t_in,
                text=True,
                capture_output=True,
                timeout=timeout_sec,
            )
            if proc.returncode != 0:
                err_msg = proc.stderr.strip().splitlines()[-1] if proc.stderr else "Runtime Error"
                return False, f"Test #{idx+1} Runtime Error: {err_msg}"

            actual_out = proc.stdout.strip()
            norm_actual = "\n".join(line.strip() for line in actual_out.splitlines() if line.strip())
            norm_expected = "\n".join(line.strip() for line in t_out.splitlines() if line.strip())

            if norm_actual != norm_expected:
                return False, (
                    f"Test #{idx+1} Wrong Answer! Expected: '{norm_expected[:100]}', Got: '{norm_actual[:100]}'"
                )

        except subprocess.TimeoutExpired:
            return False, f"Test #{idx+1} Time Limit Exceeded (>{timeout_sec}s)!"
        except Exception as e:
            return False, f"Test #{idx+1} Execution failed: {e}"

    return True, f"Passed all {len(all_tests)} tests successfully!"



def clean_and_parse_json(raw_text: str) -> dict | None:
    """TrÃ­ch xuáº¥t vÃ  lÃ m sáº¡ch JSON tá»« pháº£n há»“i LLM má»™t cÃ¡ch an toÃ n vÃ  máº¡nh máº½ (tÄƒng tá»‘c qua C++ Native Core)."""
    if not raw_text:
        return None

    from cpp_core.bridge import fast_extract_json

    cleaned = fast_extract_json(raw_text).strip()
    if not cleaned:
        cleaned = raw_text.strip()
        if "```" in cleaned:
            code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if code_block:
                cleaned = code_block.group(1).strip()
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            cleaned = cleaned[start_brace : end_brace + 1]

    # Sá»­a cÃ¡c lá»—i cÃº phÃ¡p phá»• biáº¿n cá»§a LLM nhá»
    # 1. Sá»­a lá»—i double colon hoáº·c duplicate quotes nhÆ° "id":":
    cleaned = re.sub(r'":":\s*', '": "', cleaned)
    cleaned = re.sub(r'":\s*":', '":', cleaned)
    # 2. Sá»­a dáº¥u pháº©y thá»«a trÆ°á»›c } hoáº·c ]
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Thá»­ parse báº±ng regex trÃ­ch xuáº¥t tá»«ng trÆ°á»ng náº¿u JSON bá»‹ cáº¯t cá»¥t nháº¹
    try:
        data = {}
        id_m = re.search(r'"id"\s*:\s*"([^"]+)"', cleaned)
        name_m = re.search(r'"name"\s*:\s*"([^"]+)"', cleaned)
        stmt_m = re.search(r'"statement"\s*:\s*"([\s\S]*?)"\s*,\s*"input_format"', cleaned)
        in_m = re.search(r'"input_format"\s*:\s*"([\s\S]*?)"\s*,\s*"output_format"', cleaned)
        out_m = re.search(r'"output_format"\s*:\s*"([\s\S]*?)"\s*,\s*"constraints"', cleaned)
        cons_m = re.search(r'"constraints"\s*:\s*"([\s\S]*?)"\s*,\s*"sample_input"', cleaned)
        sin_m = re.search(r'"sample_input"\s*:\s*"([\s\S]*?)"\s*,\s*"sample_output"', cleaned)
        sout_m = re.search(r'"sample_output"\s*:\s*"([\s\S]*?)"\s*,\s*"secret_tests"', cleaned)

        if id_m: data["id"] = id_m.group(1)
        if name_m: data["name"] = name_m.group(1)
        if stmt_m: data["statement"] = stmt_m.group(1).replace("\\n", "\n")
        if in_m: data["input_format"] = in_m.group(1).replace("\\n", "\n")
        if out_m: data["output_format"] = out_m.group(1).replace("\\n", "\n")
        if cons_m: data["constraints"] = cons_m.group(1).replace("\\n", "\n")
        if sin_m: data["sample_input"] = sin_m.group(1).replace("\\n", "\n")
        if sout_m: data["sample_output"] = sout_m.group(1).replace("\\n", "\n")

        # TrÃ­ch xuáº¥t secret_tests vÃ  solution_code
        sec_m = re.search(r'"secret_tests"\s*:\s*(\[[\s\S]*?\])\s*,\s*"solution_code"', cleaned)
        if sec_m:
            try:
                data["secret_tests"] = json.loads(sec_m.group(1))
            except Exception:
                data["secret_tests"] = []

        sol_m = re.search(r'"solution_code"\s*:\s*"([\s\S]*?)"\s*}?$', cleaned)
        if sol_m:
            data["solution_code"] = sol_m.group(1).replace("\\n", "\n").replace('\\"', '"')

        if data.get("statement") and (data.get("sample_input") or data.get("sample_output")):
            return data
    except Exception:
        pass

    return None


class QwenProblemGenerator:
    """Bá»™ táº¡o & BÃ³c tÃ¡ch Ä‘á» bÃ i Competitive Programming tá»± Ä‘á»™ng dÃ¹ng Qwen3-4B-Instruct-2507."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        verifier_model: str | None = None,
        backup_model: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model_name or getattr(settings, "AI_MODEL", AI_MODEL_NAME)
        self.verifier_model = verifier_model or getattr(settings, "AI_VERIFIER_MODEL", AI_VERIFIER_MODEL_NAME)
        self.backup_model = backup_model or getattr(settings, "AI_BACKUP_MODEL", AI_BACKUP_MODEL_NAME)
        self.timeout = timeout or getattr(settings, "OLLAMA_TIMEOUT", 1800)
        self.models_dir = MODELS_DIR

    def _unload_model(self, model_name: str):
        """Giáº£i phÃ³ng model khá»i RAM Ollama ngay láº­p tá»©c (keep_alive: 0) Ä‘á»ƒ tá»‘i Æ°u bá»™ nhá»› mÃ¡y."""
        try:
            payload = {"model": model_name, "keep_alive": 0}
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as res:
                pass
            logger.info(f"[RAM Optimization] ÄÃ£ giáº£i phÃ³ng model '{model_name}' khá»i RAM.")
        except Exception as e:
            logger.debug(f"[RAM Optimization] Ghi chÃº unload '{model_name}': {e}")

    def _query_ollama(
        self,
        model: str,
        prompt: str,
        num_predict: int = 1500,
        temperature: float = 0.2,
        unload_after: bool = True,
    ) -> tuple[dict[str, Any] | None, str]:
        """Gá»i Ollama generate API cÃ³ kiá»ƒm soÃ¡t bá»™ nhá»› RAM tuáº§n tá»± vÃ  trÃ­ch xuáº¥t JSON."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "keep_alive": 0 if unload_after else -1,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "repeat_penalty": 1.15,
                "num_ctx": 3072,
                "num_predict": num_predict,
                "num_thread": 4,
                **_gpu_option(),
            },
        }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                if res.status != 200:
                    return None, f"Ollama HTTP {res.status}"
                raw_resp = json.loads(res.read().decode("utf-8"))
                raw_text = raw_resp.get("response", "").strip()
                data = clean_and_parse_json(raw_text)
                return data, raw_text
        except Exception as e:
            return None, str(e)
        finally:
            if unload_after:
                self._unload_model(model)

    def check_connection(self) -> tuple[bool, str]:
        """Kiá»ƒm tra xem Ollama cÃ³ Ä‘ang cháº¡y vÃ  danh sÃ¡ch model (Qwen 3.5, Gemma 3) cÃ³ sáºµn khÃ´ng."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    has_gen = any(
                        self.model == m or m.startswith(f"{self.model}:") or self.model.split(":")[0] in m
                        for m in models
                    )
                    has_verifier = any(
                        self.verifier_model == m or m.startswith(f"{self.verifier_model}:") or self.verifier_model.split(":")[0] in m
                        for m in models
                    )
                    status_parts = []
                    if has_gen:
                        status_parts.append(f"Generator ({self.model}): OK")
                    else:
                        status_parts.append(f"Generator ({self.model}): ChÆ°a táº£i")
                    if has_verifier:
                        status_parts.append(f"Verifier ({self.verifier_model}): OK")
                    else:
                        status_parts.append(f"Verifier ({self.verifier_model}): ChÆ°a táº£i (sáº½ dÃ¹ng Single-Stage Fallback)")

                    return True, " | ".join(status_parts)
                return False, f"Ollama HTTP {res.status}"
        except urllib.error.URLError as e:
            return False, f"KhÃ´ng thá»ƒ káº¿t ná»‘i Ä‘áº¿n Ollama táº¡i {self.base_url}: {e.reason}"
        except Exception as e:
            return False, f"Lá»—i kiá»ƒm tra Ollama: {e}"

    def build_prompt(self, tier: str, theme: str) -> str:
        """XÃ¢y dá»±ng prompt chi tiáº¿t vá»›i bá»™ tiÃªu chÃ­ tá»± Ä‘Ã¡nh giÃ¡ Ä‘á»™ khÃ³ chá»‘ng láº¡m phÃ¡t rating."""
        guide = TIER_GUIDELINES.get(tier, TIER_GUIDELINES["T6"])
        division = guide["division"]
        rating = guide["rating"]
        topics = guide["topics"]
        constraints = guide["constraints"]
        complexity = guide["time_complexity"]

        # Bá»™ tiÃªu chÃ­ tá»± Ä‘Ã¡nh giÃ¡ Ä‘á»™ khÃ³ tÆ°Æ¡ng á»©ng tá»«ng báº­c
        difficulty_check = {
            "T8": "Lá»i giáº£i chá»‰ cáº§n duyá»‡t O(N) hoáº·c cÃ´ng thá»©c sá»‘ há»c cÆ¡ báº£n. Náº¿u implementation quÃ¡ Ä‘Æ¡n giáº£n (< 10 dÃ²ng logic), bÃ i pháº£i náº±m á»Ÿ T8.",
            "T7": "Lá»i giáº£i cáº§n prefix sum 1D, sÃ ng nguyÃªn tá»‘ O(N log log N), hoáº·c sort Ä‘Æ¡n giáº£n. KhÃ´ng cáº§n insight phá»©c táº¡p.",
            "T6": "Lá»i giáº£i cáº§n Greedy hoáº·c Kadane O(N), Sliding Window cÆ¡ báº£n. KhÃ´ng cáº§n káº¿t há»£p nhiá»u ká»¹ thuáº­t.",
            "T5": "Lá»i giáº£i Báº®T BUá»˜C cáº§n Cháº·t nhá»‹ phÃ¢n káº¿t quáº£ (Binary Search on Answer) HOáº¶C Two Pointers Ä‘áº¿m cáº·p cÃ³ Ä‘iá»u kiá»‡n phá»©c táº¡p. Programmer 1300 pts cáº§n 15-20 phÃºt.",
            "T4": "Lá»i giáº£i Báº®T BUá»˜C cáº§n 0/1 Knapsack vá»›i tá»‘i Æ°u hÃ³a vÃ  truy váº¿t, hoáº·c Multi-source BFS trÃªn lÆ°á»›i. Programmer 1500 pts cáº§n 20-30 phÃºt.",
            "T3": "Lá»i giáº£i Báº®T BUá»˜C cáº§n 2D Grid DP cÃ³ váº­t cáº£n & modulo 10^9+7, hoáº·c Topo Sort vá»›i thá»© tá»± tá»« Ä‘iá»ƒn nhá» nháº¥t (Kahn + min-heap). Programmer 1750 pts cáº§n 30-40 phÃºt.",
            "LT2": "Lá»i giáº£i Báº®T BUá»˜C cáº§n Segment Tree vá»›i Lazy Propagation (cáº­p nháº­t Ä‘oáº¡n & truy váº¥n Ä‘oáº¡n) hoáº·c Binary Lifting LCA. Báº®T BUá»˜C 3 SUBTASKS.",
            "MT2": "Lá»i giáº£i Báº®T BUá»˜C cáº§n State-space Dijkstra (Dijkstra trÃªn Ä‘á»“ thá»‹ phÃ¢n táº§ng vá»›i K láº§n Æ°u tiÃªn cáº¡nh) hoáº·c Tarjan tÃ¬m Cáº§u/Khá»›p. Báº®T BUá»˜C 3 SUBTASKS.",
            "HT2": "Lá»i giáº£i Báº®T BUá»˜C cáº§n Rerooting Tree DP (All-roots DP) hoáº·c Heavy-Light Decomposition (HLD) Ä‘Æ°á»ng Ä‘i trÃªn cÃ¢y. Báº®T BUá»˜C 3 SUBTASKS.",
            "LT1": "Lá»i giáº£i Báº®T BUá»˜C cáº§n mÃ´ hÃ¬nh hÃ³a Min-Cut (Project Selection) hoáº·c Persistent Segment Tree. Báº®T BUá»˜C 3 SUBTASKS.",
            "MT1": "Lá»i giáº£i Báº®T BUá»˜C cáº§n Centroid Decomposition hoáº·c FFT/NTT. Báº®T BUá»˜C 3 SUBTASKS.",
            "HT1": "Lá»i giáº£i Báº®T BUá»˜C cáº§n LÅ©y thá»«a ma tráº­n trÃªn Semi-ring (min, +) hoáº·c Suffix Automaton. Báº®T BUá»˜C 3 SUBTASKS.",
        }.get(tier, "")

        return f"""Báº¡n lÃ  ChuyÃªn gia ra Ä‘á» thi Olympic Tin há»c / Competitive Programming hÃ ng Ä‘áº§u cho Codeforces vÃ  VNOI.
Nhiá»‡m vá»¥: Táº¡o má»™t bÃ i toÃ¡n thuáº­t toÃ¡n Má»šI 100%, Äá»˜C ÄÃO, CHI TIáº¾T & HÃ“C BÃšA gáº¯n liá»n vá»›i chá»§ Ä‘á» thá»±c táº¿: "{theme}".

YÃŠU Cáº¦U Äáº¶C Táº¢ BÃ€I TOÃN TOÃ€N DIá»†N (Äáº¦Y Äá»¦ 7 Má»¤C):
- Báº­c Rank: {tier} ({division} - Rating: {rating} pts)
- Thuáº­t toÃ¡n trá»ng tÃ¢m: {topics}
- RÃ ng buá»™c dá»¯ liá»‡u: {constraints}
- Äá»™ phá»©c táº¡p thá»i gian má»¥c tiÃªu: {complexity}

TIÃŠU CHUáº¨N Äá»˜ KHÃ“ THá»°C Táº¾ (QUAN TRá»ŒNG NHáº¤T - CHá»NG Láº M PHÃT RATING):
{difficulty_check}

TUYá»†T Äá»I KHÃ”NG ÄÆ¯á»¢C GÃN RATING CAO KHI:
- Lá»i giáº£i chá»‰ lÃ  template thuáº­t toÃ¡n giÃ¡o trÃ¬nh cÆ¡ báº£n (vÃ­ dá»¥ Dijkstra 1 nguá»“n cÆ¡ báº£n hoáº·c Fenwick point-update thÃ´ng thÆ°á»ng chá»‰ thuá»™c má»©c 1300-1500 pts, KHÃ”NG ÄÆ¯á»¢C gÃ¡n lÃªn 2000-2200 pts).
- Lá»i giáº£i chá»‰ cáº§n duyá»‡t máº£ng Ä‘Æ¡n giáº£n hoáº·c 1 cÃ´ng thá»©c DP 1D trá»±c tiáº¿p.
- KhÃ´ng cÃ³ insight khÃ³, khÃ´ng cÃ³ mÃ´ hÃ¬nh hÃ³a hoáº·c observation khÃ´ng hiá»ƒn nhiÃªn.
- Implementation ngáº¯n hÆ¡n 25 dÃ²ng logic thá»±c sá»±.
- KhÃ´ng phÃ¢n chia 3 Subtasks rÃµ rÃ ng Ä‘á»‘i vá»›i cÃ¡c bÃ i tá»« báº­c LT2 trá»Ÿ lÃªn.
- Má»™t programmer á»Ÿ rating THáº¤P HÆ N 200 pts cÃ³ thá»ƒ giáº£i Ä‘Æ°á»£c dá»… dÃ ng trong 10 phÃºt.

QUY Táº®C Ná»˜I DUNG CHI TIáº¾T:
1. Äá»€ BÃ€I (statement): Viáº¿t chi tiáº¿t, chuyÃªn sÃ¢u, cá»‘t truyá»‡n háº¥p dáº«n vÃ  hÃ³c bÃºa (200-350 tá»«). BÃ i toÃ¡n pháº£i cÃ³ sá»± chuyá»ƒn Ä‘á»•i tráº¡ng thÃ¡i phá»©c táº¡p, khÃ´ng hiá»ƒn nhiÃªn tá»« Ä‘á» bÃ i sang thuáº­t toÃ¡n.
2. INPUT FORMAT (input_format): MÃ´ táº£ chi tiáº¿t tá»«ng dÃ²ng dá»¯ liá»‡u Ä‘áº§u vÃ o theo dáº¡ng gáº¡ch Ä‘áº§u dÃ²ng.
3. OUTPUT FORMAT (output_format): Quy Ä‘á»‹nh chuáº©n xÃ¡c Ä‘á»‹nh dáº¡ng Ä‘áº§u ra, xá»­ lÃ½ trÆ°á»ng há»£p Ä‘áº·c biá»‡t.
4. RÃ€NG BUá»˜C & 3 SUBTASKS (Báº®T BUá»˜C Tá»ª LT2 Äáº¾N HT1): Äá»‘i vá»›i báº­c LT2, MT2, HT2, LT1, MT1, HT1, Báº®T BUá»˜C PHáº¢I CÃ“ ÄÃšNG 3 SUBTASKS (Subtask 1: 25-30% duyá»‡t trÃ¢u, Subtask 2: 30-35% quy hoáº¡ch Ä‘á»™ng/trung gian, Subtask 3: 40% giáº£i thuáº­t tá»‘i Æ°u), thá»i gian 2.0s, RAM 512MB.
5. VÃ Dá»¤ MáºªU (sample_input & sample_output): Bá»™ dá»¯ liá»‡u máº«u phong phÃº, chuáº©n xÃ¡c 100%.
6. TEST áº¨N (secret_tests): Cung cáº¥p tá»« 4 Ä‘áº¿n 6 bá»™ test áº©n Ä‘a dáº¡ng (test nhá», lá»›n, biÃªn, case Ä‘áº·c biá»‡t).
7. HÆ¯á»šNG DáºªN GIáº¢I THUáº¬T & CODE (solution_code): Cung cáº¥p giáº£i thuáº­t Python 3 chuáº©n xÃ¡c kÃ¨m chÃº thÃ­ch tá»«ng bÆ°á»›c.

Tráº£ vá» DUY NHáº¤T má»™t JSON há»£p lá»‡ (khÃ´ng kÃ¨m markdown):
{{
  "id": "duel_{tier.lower()}_ten_bai_khong_dau",
  "name": "TÃªn BÃ i ToÃ¡n ChuyÃªn SÃ¢u",
  "statement": "Ná»™i dung Ä‘á» bÃ i chi tiáº¿t, sÃ¢u sáº¯c vÃ  thá»±c táº¿...",
  "input_format": "â€¢ DÃ²ng 1: Chá»©a hai sá»‘ nguyÃªn n vÃ  k...\nâ€¢ DÃ²ng 2: Chá»©a dÃ£y sá»‘...",
  "output_format": "In ra má»™t sá»‘ nguyÃªn duy nháº¥t thá»a mÃ£n yÃªu cáº§u bÃ i toÃ¡n...",
  "constraints": "{constraints}. Giá»›i háº¡n: 2.0s, 512MB.",
  "sample_input": "3 3\n0 1 0\n0 0 1\n1 0 0",
  "sample_output": "0",
  "secret_tests": [
    {{"input": "1 1\n0", "output": "0"}},
    {{"input": "2 2\n1 1\n1 0", "output": "2"}}
  ],
  "solution_code": "# [1] Äá»c dá»¯ liá»‡u Ä‘áº§u vÃ o\nimport sys\n\ndef main():\n    data = sys.stdin.read().split()\n    if not data: return\n    # [2] Thá»±c thi giáº£i thuáº­t chÃ­nh\n    pass\n\nif __name__ == '__main__': main()"
}}"""

    def generate_problem_sync(
        self,
        tier: str = "T6",
        theme: str | None = None,
        max_retries: int = 2,
    ) -> tuple[DuelProblem | None, str]:
        """
        Quy trÃ¬nh táº¡o bÃ i táº­p 3 bÆ°á»›c chuyÃªn sÃ¢u (Qwen 3.5:4B & Gemma 3:4B Pipeline):
        1. BÆ°á»›c 1 (Generator - Qwen 3.5:4B / Backup 2B): Sinh báº£n tháº£o ban Ä‘áº§u gá»“m Ä‘á» bÃ i, cá»‘t truyá»‡n, test cases vÃ  solution.
        2. BÆ°á»›c 2 (Verifier & Enhancer - Gemma 3:4B): Kiá»ƒm tra tÃ­nh Ä‘Ãºng Ä‘áº¯n logic, rÃ ng buá»™c toÃ¡n há»c, nÃ¢ng cáº¥p Ä‘á»™ dÃ i vÃ  má»Ÿ rá»™ng test case biÃªn.
        3. BÆ°á»›c 3 (Tester & Solver - Qwen 3.5:4B): Thá»­ nghiá»‡m nghiá»‡m thu code giáº£i thuáº­t. Náº¿u sai Ä‘Æ°á»£c sá»­a code, nhÆ°ng TUYá»†T Äá»I KHÃ”NG lÃ m thay Ä‘á»•i bÃ i cá»§a Gemma 3:4B Ä‘Ã£ hoÃ n thiá»‡n.
        """
        tier = tier.upper()
        if tier not in TIER_GUIDELINES:
            tier = "T6"

        theme = theme or random.choice(DEFAULT_THEMES)
        guide = TIER_GUIDELINES[tier]
        prompt_stage1 = self.build_prompt(tier, theme)

        total_start = time.time()

        for attempt in range(1, max_retries + 1):
            try:
                # -------------------------------------------------------------
                # GIAI ÄOáº N 1: Qwen 3.5:4b (hoáº·c Backup) táº¡o báº£n tháº£o ban Ä‘áº§u
                # -------------------------------------------------------------
                logger.info(f"[Pipeline BÆ°á»›c 1/3] Qwen ({self.model}) Ä‘ang sinh báº£n tháº£o Ä‘á» bÃ i '{theme}' (Láº§n #{attempt})...")
                draft_data, draft_raw = self._query_ollama(
                    model=self.model,
                    prompt=prompt_stage1,
                    num_predict=1200,
                    temperature=0.2,
                    unload_after=True,
                )

                # Náº¿u model chÃ­nh lá»—i, thá»­ fallback sang model dá»± phÃ²ng (qwen3.5:2b)
                if not draft_data and self.backup_model and self.backup_model != self.model:
                    logger.warning(f"[Pipeline Fallback] Qwen ({self.model}) chÆ°a sáºµn sÃ ng, chuyá»ƒn sang backup ({self.backup_model})...")
                    draft_data, draft_raw = self._query_ollama(
                        model=self.backup_model,
                        prompt=prompt_stage1,
                        num_predict=1200,
                        temperature=0.2,
                        unload_after=True,
                    )

                if not draft_data:
                    if attempt < max_retries:
                        continue
                    return None, f"[BÆ°á»›c 1 Tháº¥t báº¡i] KhÃ´ng trÃ­ch xuáº¥t Ä‘Æ°á»£c JSON tá»« Qwen: {draft_raw[:200]}"

                prob_id = draft_data.get("id", f"duel_{tier.lower()}_{int(time.time())}")
                prob_name = draft_data.get("name", f"Thá»­ ThÃ¡ch {theme.title()}")
                statement = draft_data.get("statement", "")
                in_fmt = draft_data.get("input_format", "")
                out_fmt = draft_data.get("output_format", "")
                constraints = draft_data.get("constraints", "")
                s_in = str(draft_data.get("sample_input", "")).strip()
                s_out = str(draft_data.get("sample_output", "")).strip()
                secret_tests = draft_data.get("secret_tests", [])
                sol_code = draft_data.get("solution_code", "")

                if not statement or not s_in or not s_out or not sol_code:
                    if attempt < max_retries:
                        continue
                    return None, "[BÆ°á»›c 1 Tháº¥t báº¡i] Báº£n tháº£o Qwen thiáº¿u cÃ¡c trÆ°á»ng ná»™i dung cá»‘t lÃµi!"

                # -------------------------------------------------------------
                # GIAI ÄOáº N 2: Gemma 3:4B Kiá»ƒm tra, NÃ¢ng cáº¥p Ä‘á»™ dÃ i & Logic bÃ i
                # -------------------------------------------------------------
                enhanced_by_gemma = False
                logger.info(f"[Pipeline BÆ°á»›c 2/3] Gemma ({self.verifier_model}) Ä‘ang tháº©m Ä‘á»‹nh & nÃ¢ng cáº¥p logic/Ä‘á»™ dÃ i...")

                prompt_gemma = f"""Báº¡n lÃ  ChuyÃªn gia Tháº©m Ä‘á»‹nh & Tá»‘i Æ°u Äá» thi Olympic Tin há»c Quá»‘c Táº¿ (Gemma 3:4B).
Nhiá»‡m vá»¥: Äá»c báº£n tháº£o bÃ i toÃ¡n do Qwen táº¡o ra dÆ°á»›i Ä‘Ã¢y, KIá»‚M TRA TOÃ€N DIá»†N vÃ  NÃ‚NG Cáº¤P Äá»˜ DÃ€I, CHIá»€U SÃ‚U VÃ€ TÃNH CHáº¶T CHáº¼ Cá»¦A LOGIC.

Báº¢N THáº¢O Tá»ª QWEN:
- TiÃªu Ä‘á»: {prob_name}
- Cá»‘t truyá»‡n Ä‘á» bÃ i: {statement}
- RÃ ng buá»™c: {constraints}
- Äá»‹nh dáº¡ng Input: {in_fmt}
- Äá»‹nh dáº¡ng Output: {out_fmt}
- Sample Input: {s_in}
- Sample Output: {s_out}
- Secret Tests: {json.dumps(secret_tests, ensure_ascii=False)}

YÃŠU Cáº¦U NÃ‚NG Cáº¤P Báº®T BUá»˜C Tá»ª GEMMA:
1. NÃ‚NG Cáº¤P Äá»˜ DÃ€I & VÄ‚N PHONG LOGIC: Má»Ÿ rá»™ng Ä‘á» bÃ i (statement) dÃ i hÆ¡n (250-400 tá»«), cá»‘t truyá»‡n sÃ¢u sáº¯c, há»c thuáº­t vÃ  chi tiáº¿t hÆ¡n, loáº¡i bá» má»i gÃ³c khuáº¥t gÃ¢y hiá»ƒu nháº§m cho thÃ­ sinh.
2. CHáº¶T CHáº¼ HÃ“A RÃ€NG BUá»˜C: Äáº£m báº£o thá»i gian 2.0s, RAM 512MB vÃ  cÃ¡c biáº¿n sá»‘ (N, K, A_i) hoÃ n toÃ n kháº£ thi vá»›i Ä‘á»™ phá»©c táº¡p bÃ i toÃ¡n, cáº£nh bÃ¡o nguy cÆ¡ trÃ n sá»‘ nguyÃªn (64-bit integer overflow).
3. Bá»” SUNG TEST CASE BáºªY/BIÃŠN: Chuáº©n hÃ³a láº¡i sample test vÃ  bá»• sung Ã­t nháº¥t 2-3 test cases biÃªn (Corner cases: N=1, sá»‘ 0, sá»‘ Ã¢m, máº£ng cá»±c Ä‘áº¡i) vÃ o 'secret_tests'.

Tráº£ vá» DUY NHáº¤T má»™t JSON há»£p lá»‡:
{{
  "name": "{prob_name}",
  "statement": "Ná»™i dung Ä‘á» bÃ i chi tiáº¿t Ä‘Ã£ Ä‘Æ°á»£c Gemma nÃ¢ng cáº¥p Ä‘á»™ dÃ i vÃ  logic...",
  "input_format": "MÃ´ táº£ input chi tiáº¿t...",
  "output_format": "MÃ´ táº£ output chi tiáº¿t...",
  "constraints": "{constraints}",
  "sample_input": "{s_in}",
  "sample_output": "{s_out}",
  "secret_tests": [
    {{"input": "...", "output": "..."}}
  ]
}}"""

                gemma_data, gemma_raw = self._query_ollama(
                    model=self.verifier_model,
                    prompt=prompt_gemma,
                    num_predict=1500,
                    temperature=0.2,
                    unload_after=True,
                )

                if gemma_data and gemma_data.get("statement") and gemma_data.get("sample_input"):
                    logger.info("[Pipeline BÆ°á»›c 2/3] Gemma 3:4B Ä‘Ã£ kiá»ƒm tra vÃ  nÃ¢ng cáº¥p thÃ nh cÃ´ng logic/Ä‘á»™ dÃ i Ä‘á» bÃ i!")
                    prob_name = gemma_data.get("name", prob_name)
                    statement = gemma_data.get("statement", statement)
                    in_fmt = gemma_data.get("input_format", in_fmt)
                    out_fmt = gemma_data.get("output_format", out_fmt)
                    constraints = gemma_data.get("constraints", constraints)
                    s_in = str(gemma_data.get("sample_input", s_in)).strip()
                    s_out = str(gemma_data.get("sample_output", s_out)).strip()
                    if gemma_data.get("secret_tests"):
                        secret_tests = gemma_data.get("secret_tests")
                    enhanced_by_gemma = True
                else:
                    logger.warning(f"[Pipeline BÆ°á»›c 2/3] Gemma ({self.verifier_model}) chÆ°a pháº£n há»“i hoáº·c chÆ°a táº£i, tiáº¿p tá»¥c vá»›i báº£n tháº£o chuáº©n.")

                # -------------------------------------------------------------
                # GIAI ÄOáº N 3: Qwen 3.5:4b test & sá»­a code náº¿u cáº§n (KHÃ”NG Sá»¬A Äá»€ Cá»¦A GEMMA)
                # -------------------------------------------------------------
                logger.info(f"[Pipeline BÆ°á»›c 3/3] Qwen ({self.model}) Ä‘ang kiá»ƒm thá»­ nghiá»‡m thu code giáº£i...")
                is_valid, val_msg = validate_python_solution(sol_code, s_in, s_out, secret_tests)

                if not is_valid:
                    logger.info(f"[Pipeline BÆ°á»›c 3/3] Code ban Ä‘áº§u chÆ°a pass ({val_msg}), yÃªu cáº§u Qwen sá»­a code theo chuáº©n cá»§a Gemma...")
                    prompt_qwen_solve = f"""Báº¡n lÃ  ChuyÃªn gia Thuáº­t toÃ¡n Solver (Qwen 3.5:4B).
BÃ i toÃ¡n sau Ä‘Ã¢y Ä‘Ã£ Ä‘Æ°á»£c Tháº©m Ä‘á»‹nh viÃªn Gemma 3:4B kiá»ƒm tra, nÃ¢ng cáº¥p vÃ  chá»‘t cáº¥u trÃºc:

TÃŠN BÃ€I: {prob_name}
Äá»€ BÃ€I: {statement}
INPUT FORMAT: {in_fmt}
OUTPUT FORMAT: {out_fmt}
RÃ€NG BUá»˜C: {constraints}
SAMPLE INPUT:
{s_in}
SAMPLE OUTPUT:
{s_out}
SECRET TESTS:
{json.dumps(secret_tests, ensure_ascii=False)}

TÃŒNH TRáº NG Lá»–I Cá»¦A CODE HIá»†N Táº I:
{val_msg}

NHIá»†M Vá»¤:
HÃ£y viáº¿t láº¡i mÃ£ nguá»“n Python 3 (solution_code) chuáº©n xÃ¡c, tá»‘i Æ°u Ä‘á»ƒ vÆ°á»£t qua 100% cÃ¡c test cases trÃªn.

âš ï¸ QUY Táº®C Báº®T BUá»˜C (QUAN TRá»ŒNG NHáº¤T):
- Báº¡n TUYá»†T Äá»I KHÃ”NG ÄÆ¯á»¢C LÃ€M THAY Äá»”I Ä‘á» bÃ i, tÃªn bÃ i, rÃ ng buá»™c hay báº¥t ká»³ test case nÃ o do Gemma 3:4B Ä‘Ã£ hoÃ n thiá»‡n!
- Báº¡n CHá»ˆ ÄÆ¯á»¢C PHÃ‰P sá»­a Ä‘á»•i vÃ  hoÃ n thiá»‡n duy nháº¥t mÃ£ nguá»“n 'solution_code'.

Tráº£ vá» DUY NHáº¤T má»™t JSON há»£p lá»‡:
{{
  "solution_code": "import sys\\n\\ndef main():\\n    pass\\n\\nif __name__ == '__main__':\\n    main()"
}}"""
                    solve_data, solve_raw = self._query_ollama(
                        model=self.model,
                        prompt=prompt_qwen_solve,
                        num_predict=1000,
                        temperature=0.1,
                        unload_after=True,
                    )
                    if solve_data and solve_data.get("solution_code"):
                        new_sol_code = solve_data.get("solution_code")
                        new_valid, new_val_msg = validate_python_solution(new_sol_code, s_in, s_out, secret_tests)
                        if new_valid:
                            sol_code = new_sol_code
                            is_valid = True
                            val_msg = f"Qwen fix code thÃ nh cÃ´ng: {new_val_msg}"
                        else:
                            val_msg = f"Qwen fix code láº§n 2 chÆ°a qua: {new_val_msg}"

                parsed_rating = int(guide["rating"].replace(" pts", "").strip())
                problem = DuelProblem(
                    id=prob_id,
                    name=prob_name,
                    tier=tier,
                    division=guide["division"],
                    rating_display=f"{tier} / Rating: {guide['rating']}",
                    statement=statement,
                    input_format=in_fmt,
                    output_format=out_fmt,
                    constraints=constraints,
                    sample_input=s_in,
                    sample_output=s_out,
                    secret_tests=secret_tests,
                    time_limit_minutes=guide["time"],
                    max_code_size_kb=guide["kb"],
                    solution_code=sol_code,
                    rating=parsed_rating,
                    tags=draft_data.get("tags", [guide["topics"].split(",")[0].strip()]),
                    time_limit_sec=2.0 if tier in ["LT2", "MT2", "HT2", "LT1", "MT1", "HT1"] else 1.0,
                    memory_limit_mb=512 if tier in ["LT2", "MT2", "HT2", "LT1", "MT1", "HT1"] else 256,
                    sample_explanation=draft_data.get("sample_explanation", ""),
                )

                elapsed = time.time() - total_start
                pipeline_note = "Qwen3.5 4B + Gemma4 e4B Pipeline" if enhanced_by_gemma else "Qwen3.5 4B Direct Pipeline"
                return problem, f"Táº¡o thÃ nh cÃ´ng Ä‘á» bÃ i '{prob_name}' [{pipeline_note}] ({elapsed:.1f}s, {val_msg})"

            except urllib.error.URLError as e:
                return None, f"Lá»—i káº¿t ná»‘i Ollama: {e.reason}"
            except Exception as e:
                if attempt >= max_retries:
                    return None, f"Lá»—i sinh Ä‘á»: {e}"

        return None, "Háº¿t sá»‘ láº§n thá»­ láº¡i!"

    def extract_problem_from_raw_text(
        self,
        raw_text: str,
        tier: str = "T6",
    ) -> tuple[DuelProblem | None, str]:
        """
        PhÃ¢n tÃ­ch vÄƒn báº£n thÃ´ (copy tá»« web/PDF/chat) vÃ  chá»‰ bÃ³c tÃ¡ch:
        - Äá» bÃ i (statement)
        - Input Format (input_format)
        - Output Format (output_format)
        - RÃ ng buá»™c (constraints)
        - VÃ­ dá»¥ máº«u (sample_input, sample_output)
        Äá»“ng thá»i dÃ¹ng AI Core (Qwen3-4B-Instruct-2507) Ä‘á»ƒ tá»± Ä‘á»™ng sinh secret_tests vÃ  solution_code.
        """
        tier = tier.upper()
        if tier not in TIER_GUIDELINES:
            tier = "T6"
        guide = TIER_GUIDELINES[tier]

        prompt = f"""Báº¡n lÃ  má»™t chuyÃªn gia phÃ¢n tÃ­ch Ä‘á» bÃ i Competitive Programming.
DÆ°á»›i Ä‘Ã¢y lÃ  má»™t Ä‘oáº¡n vÄƒn báº£n thÃ´ chá»©a ná»™i dung bÃ i toÃ¡n (cÃ³ thá»ƒ copy tá»« Codeforces, LeetCode, VNOI hoáº·c PDF):

--- Báº®T Äáº¦U VÄ‚N Báº¢N THÃ” ---
{raw_text}
--- Káº¾T THÃšC VÄ‚N Báº¢N THÃ” ---

NHIá»†M Vá»¤:
1. HÃ£y phÃ¢n tÃ­ch vÃ  BÃ“C TÃCH CHÃNH XÃC cÃ¡c pháº§n:
   - "name": TÃªn bÃ i toÃ¡n tiáº¿ng Viá»‡t hoáº·c tiáº¿ng Anh chuáº©n.
   - "statement": CHá»ˆ ná»™i dung mÃ´ táº£ Ä‘á» bÃ i / cá»‘t truyá»‡n (khÃ´ng chá»©a pháº§n Input/Output/VÃ­ dá»¥).
   - "input_format": CHá»ˆ mÃ´ táº£ Ä‘á»‹nh dáº¡ng Ä‘áº§u vÃ o.
   - "output_format": CHá»ˆ mÃ´ táº£ Ä‘á»‹nh dáº¡ng Ä‘áº§u ra.
   - "constraints": RÃ ng buá»™c toÃ¡n há»c vÃ  kÃ­ch thÆ°á»›c (vÃ­ dá»¥: 1 <= N <= 10^5).
   - "sample_input": Dá»¯ liá»‡u Ä‘áº§u vÃ o vÃ­ dá»¥ (raw string, phÃ¢n cÃ¡ch dÃ²ng báº±ng \n).
   - "sample_output": Dá»¯ liá»‡u Ä‘áº§u ra vÃ­ dá»¥ (raw string).
2. Tá»± Ä‘á»™ng sinh thÃªm 5 bá»™ "secret_tests" (gá»“m input vÃ  output) Ä‘á»ƒ lÃ m test áº©n cháº¥m Ä‘iá»ƒm.
3. Tá»± Ä‘á»™ng viáº¿t mÃ£ nguá»“n Python 3 "solution_code" giáº£i bÃ i toÃ¡n nÃ y vá»›i Ä‘á»™ phá»©c táº¡p tá»‘i Æ°u.

Tráº£ vá» DUY NHáº¤T má»™t Ä‘á»‘i tÆ°á»£ng JSON há»£p lá»‡ (khÃ´ng kÃ¨m markdown):
{{
  "id": "duel_{tier.lower()}_bai_boc_tach",
  "name": "TÃªn bÃ i toÃ¡n",
  "statement": "Ná»™i dung Ä‘á» bÃ i...",
  "input_format": "MÃ´ táº£ input...",
  "output_format": "MÃ´ táº£ output...",
  "constraints": "RÃ ng buá»™c...",
  "sample_input": "...",
  "sample_output": "...",
  "secret_tests": [
    {{"input": "...", "output": "..."}}
  ],
  "solution_code": "..."
}}"""

        data, raw_resp_str = self._query_ollama(
            model=self.model,
            prompt=prompt,
            num_predict=1200,
            temperature=0.3,
            unload_after=True,
        )

        if not data:
            return None, f"KhÃ´ng thá»ƒ trÃ­ch xuáº¥t JSON tá»« bÃ i bÃ³c tÃ¡ch: {raw_resp_str[:150]}"

        try:
            prob_id = data.get("id", f"duel_{tier.lower()}_{int(time.time())}")
            prob_name = data.get("name", "BÃ i ToÃ¡n BÃ³c TÃ¡ch")
            statement = data.get("statement", "")
            in_fmt = data.get("input_format", "")
            out_fmt = data.get("output_format", "")
            constraints = data.get("constraints", "")
            s_in = str(data.get("sample_input", "")).strip()
            s_out = str(data.get("sample_output", "")).strip()
            secret_tests = data.get("secret_tests", [])
            sol_code = data.get("solution_code", "")

            if not statement or not s_in or not s_out:
                return None, "KhÃ´ng thá»ƒ bÃ³c tÃ¡ch Ä‘á»§ cÃ¡c trÆ°á»ng Äá» bÃ i/Input/Output/VÃ­ dá»¥!"

                # Tá»± Ä‘á»™ng tháº©m Ä‘á»‹nh qua Sandbox náº¿u cÃ³ solution code
                if sol_code:
                    is_valid, val_msg = validate_python_solution(sol_code, s_in, s_out, secret_tests)
                else:
                    val_msg = "ChÆ°a cÃ³ solution code"

                parsed_rating = int(guide["rating"].replace(" pts", "").strip())
                problem = DuelProblem(
                    id=prob_id,
                    name=prob_name,
                    tier=tier,
                    division=guide["division"],
                    rating_display=f"{tier} / Rating: {guide['rating']}",
                    statement=statement,
                    input_format=in_fmt,
                    output_format=out_fmt,
                    constraints=constraints,
                    sample_input=s_in,
                    sample_output=s_out,
                    secret_tests=secret_tests,
                    time_limit_minutes=guide["time"],
                    max_code_size_kb=guide["kb"],
                    solution_code=sol_code,
                    rating=parsed_rating,
                    tags=data.get("tags", [guide["topics"].split(",")[0].strip()]),
                    time_limit_sec=2.0 if tier in ["LT2", "MT2", "HT2", "LT1", "MT1", "HT1"] else 1.0,
                    memory_limit_mb=512 if tier in ["LT2", "MT2", "HT2", "LT1", "MT1", "HT1"] else 256,
                    sample_explanation=data.get("sample_explanation", ""),
                )

                return problem, f"BÃ³c tÃ¡ch thÃ nh cÃ´ng bÃ i '{prob_name}' ({val_msg})"

        except urllib.error.URLError as e:
            return None, f"Lá»—i káº¿t ná»‘i Ollama: {e.reason}"
        except Exception as e:
            return None, f"Lá»—i bÃ³c tÃ¡ch Ä‘á» bÃ i: {e}"

    async def generate_problem_async(
        self,
        tier: str = "T6",
        theme: str | None = None,
    ) -> tuple[DuelProblem | None, str]:
        """Bá»c asynchronous cho generate_problem_sync vá»›i Internet Real-World Context Feed."""
        if not theme:
            try:
                from services.online_context import get_realworld_theme
                theme = await get_realworld_theme()
            except Exception:
                theme = random.choice(DEFAULT_THEMES)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate_problem_sync, tier, theme)

    async def extract_problem_async(
        self,
        raw_text: str,
        tier: str = "T6",
    ) -> tuple[DuelProblem | None, str]:
        """Bá»c asynchronous cho extract_problem_from_raw_text."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.extract_problem_from_raw_text, raw_text, tier)


# Singleton instance
ai_generator = QwenProblemGenerator()

