"""Official Codeforces API client with async aiohttp, SHA-512 signing, rate limiting, and caching."""

import asyncio
import hashlib
import json
import random
import string
import time
from typing import Any

import aiohttp

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("CodeforcesAPI")


class CodeforcesAPIError(Exception):
    """Base exception for Codeforces API errors."""


class CodeforcesAPI:
    """Async client interacting with Codeforces official REST API."""

    BASE_URL = "https://codeforces.com/api"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout_seconds: int = 15,
        min_request_interval: float = 0.25,
    ):
        self.api_key = api_key or getattr(settings, "CF_API_KEY", "")
        self.api_secret = api_secret or getattr(settings, "CF_API_SECRET", "")
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None
        self._min_interval = min_request_interval
        self._last_request_time: float = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        loop = asyncio.get_running_loop()
        if (
            self._session is None
            or self._session.closed
            or getattr(self._session, "_loop", None) != loop
        ):
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 DiscordCPBot/2.0"
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _generate_api_sig(self, method_name: str, params: dict[str, Any]) -> str:
        """Generates 6-character random prefix SHA-512 signature for authenticated calls."""
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        sorted_params = sorted(params.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        to_hash = f"{rand}/{method_name}?{query_string}#{self.api_secret}"
        sha512_hash = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()
        return f"{rand}{sha512_hash}"

    async def _request(
        self,
        method_name: str,
        params: dict[str, Any] | None = None,
        anonymous: bool = False,
    ) -> Any:
        """Gửi HTTP request bất đồng bộ tới Codeforces API có khống chế tần suất và chữ ký SHA-512."""
        params = dict(params or {})

        # Khống chế tần suất gọi API (Rate-limiting throttle)
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

        if not anonymous and self.api_key and self.api_secret:
            params["apiKey"] = self.api_key
            params["time"] = int(time.time())
            params["apiSig"] = self._generate_api_sig(method_name, params)

        url = f"{self.BASE_URL}/{method_name}"
        session = await self._get_session()

        try:
            async with session.get(url, params=params) as resp:
                text = await resp.text()

                if resp.status == 503:
                    raise CodeforcesAPIError(
                        "⚠️ Codeforces API đang tạm bảo trì hoặc kiểm tra Cloudflare (HTTP 503)."
                    )
                if resp.status != 200:
                    raise CodeforcesAPIError(
                        f"Codeforces API HTTP {resp.status}: {text[:150]}"
                    )

                try:
                    data = json.loads(text)
                except Exception:
                    raise CodeforcesAPIError(
                        f"Phản hồi từ Codeforces không phải định dạng JSON hợp lệ (HTTP {resp.status})."
                    )

                if isinstance(data, dict):
                    if data.get("status") == "OK":
                        return data.get("result")
                    else:
                        comment = data.get("comment", "Unknown API error")
                        raise CodeforcesAPIError(f"Codeforces API Error: {comment}")
                return data
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"Lỗi kết nối tới máy chủ Codeforces: {e}")
            raise CodeforcesAPIError(
                "Lỗi kết nối mạng: Không thể kết nối tới Codeforces."
            )
        except asyncio.TimeoutError:
            logger.warning("Hết thời gian chờ phản hồi từ Codeforces API (Timeout).")
            raise CodeforcesAPIError(
                "Hết thời gian chờ Codeforces API phản hồi. Vui lòng thử lại."
            )
        except CodeforcesAPIError:
            raise
        except Exception as e:
            logger.warning(f"Lỗi khi gọi Codeforces API {method_name}: {e}")
            raise CodeforcesAPIError(f"Lỗi Codeforces API: {e!s}")

    _user_info_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    async def get_user_info(self, handle: str) -> dict[str, Any] | None:
        """Lấy thông tin tài khoản Codeforces (có bộ đệm 5 phút)."""
        handle_key = handle.strip().lower()
        now = time.time()
        if handle_key in self._user_info_cache:
            ts, cached_val = self._user_info_cache[handle_key]
            if (now - ts) < 300.0:
                return cached_val

        try:
            result = await self._request("user.info", {"handles": handle})
            if result and isinstance(result, list) and len(result) > 0:
                user_data = result[0]
                self._user_info_cache[handle_key] = (now, user_data)
                return user_data
            self._user_info_cache[handle_key] = (now, None)
            return None
        except CodeforcesAPIError as e:
            if "not found" in str(e).lower():
                self._user_info_cache[handle_key] = (now, None)
                return None
            raise

    async def get_user_submissions(
        self, handle: str, count: int = 30, from_index: int = 1
    ) -> list[dict[str, Any]]:
        """Lấy danh sách các submission gần nhất của thí sinh."""
        result = await self._request(
            "user.status", {"handle": handle, "from": from_index, "count": count}
        )
        return result or []

    async def get_problemset(self, tags: str | None = None) -> dict[str, Any]:
        """Lấy danh sách bài tập từ kho problemset."""
        params = {}
        if tags:
            params["tags"] = tags
        return await self._request("problemset.problems", params, anonymous=True)

    async def get_contest_list(self, gym: bool = False) -> list[dict[str, Any]]:
        """Lấy danh sách các cuộc thi (Contests)."""
        result = await self._request(
            "contest.list", {"gym": "true" if gym else "false"}, anonymous=True
        )
        return result or []

    async def get_contest_standings(
        self, contest_id: int, from_index: int = 1, count: int = 1, **kwargs
    ) -> dict[str, Any]:
        """Lấy danh sách bài tập và thông tin contest ở chế độ Anonymous siêu nhanh và nhẹ."""
        return await self._request(
            "contest.standings",
            {
                "contestId": contest_id,
                "from": from_index,
                "count": count,
            },
            anonymous=True,
        )


# Global Codeforces API client singleton
cf_api = CodeforcesAPI()
