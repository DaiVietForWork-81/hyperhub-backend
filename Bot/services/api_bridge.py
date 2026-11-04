"""Bot & Web API Bridge Service (HTTP REST & RPC).

Cung cấp các API RESTful để ứng dụng Web (hoặc các dịch vụ bên ngoài)
có thể giao tiếp, truy vấn dữ liệu và tương tác hai chiều với Discord Bot
bất kể Web và Bot chạy trên cùng một máy hay ở các server/cloud khác nhau.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any

import discord
from aiohttp import web
from config.settings import settings

if TYPE_CHECKING:
    from discord.ext import commands

logger = logging.getLogger("api_bridge")
START_TIME = time.time()
BOT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 4 Role Quản trị Web theo yêu cầu (Admin Console chỉ hiện với 4 role này
# + Bot Owner / Guild Owner / quyền Administrator dự phòng)
ADMIN_ROLE_IDS = {
    1534128845198987438,  # 👑 Owner
    1534132250088833024,  # 👑 Co-Owner
    1532383529353089085,  # ⚡ Administrator
    1534146463246974995,  # 🛡️ Moderator
}
BOT_OWNER_ID = 1529864608813416449
DISCORD_GUILD_ID = 1532265330079174697


class BotAPIBridge:
    """Quản lý HTTP API Server kết nối Bot với Web."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._token_cache: dict[str, tuple[dict, float]] = {}
        self._exam_rate_limits: dict[str, list[float]] = {}
        self._upload_rate_limits: dict[str, list[float]] = {}
        self._import_rate_limits: dict[str, list[float]] = {}
        self._general_rate_limits: dict[str, list[float]] = {}
        self._doc_stats_cache: tuple[dict, float] | None = None
        self._doc_min_id_cache: tuple[dict[str, tuple[int, int]], float] | None = None
        self.app = web.Application(
            client_max_size=30 * 1024 * 1024,  # Giới hạn an toàn 30 MB
            middlewares=[self._cors_middleware, self._rate_limit_middleware, self._auth_middleware],
        )
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._setup_routes()

    def invalidate_doc_caches(self) -> None:
        """Xóa cache tài liệu khi có nộp mới, sửa hoặc xóa để đảm bảo tính nhất quán tức thì."""
        self._doc_stats_cache = None
        self._doc_min_id_cache = None

    @web.middleware
    async def _rate_limit_middleware(self, request: web.Request, handler: Any) -> web.Response:
        """Kiểm soát tần suất truy cập toàn diện (Tối đa 120 req / phút / IP) chống DoS và Brute-force."""
        if request.method == "OPTIONS":
            return await handler(request)

        client_ip = request.remote or "unknown"
        now = time.time()
        history = [t for t in self._general_rate_limits.get(client_ip, []) if now - t < 60.0]
        if len(history) >= 120:
            return web.json_response(
                {
                    "error": "Too Many Requests",
                    "message": "Quá nhiều yêu cầu từ địa chỉ IP của bạn. Vui lòng thử lại sau 1 phút.",
                },
                status=429,
                headers={"Retry-After": "60"},
            )
        history.append(now)
        self._general_rate_limits[client_ip] = history
        return await handler(request)

    async def _verify_discord_bearer_token(self, token: str) -> dict | None:
        """Xác thực Bearer token trực tiếp với Discord API https://discord.com/api/users/@me.
        Có in-memory cache TTL 300 giây để tối ưu tốc độ và không spam rate limit Discord.
        """
        if not token or len(token) < 10:
            return None

        now = time.time()
        if token in self._token_cache:
            cached_user, expiry = self._token_cache[token]
            if now < expiry:
                return cached_user

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://discord.com/api/users/@me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    if resp.status == 200:
                        user_data = await resp.json()
                        self._token_cache[token] = (user_data, now + 300.0)
                        return user_data
                    else:
                        logger.warning(f"Discord API token verification failed with status {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Error verifying Discord token: {e}")
            return None

    @staticmethod
    def _is_valid_bot_api_secret(token: str) -> bool:
        """Kiểm tra token có khớp với BOT_API_SECRET hợp lệ (chống timing attack, cấm secret mặc định lộ công khai)."""
        if not token:
            return False
        configured = (getattr(settings, "BOT_API_SECRET", "") or "").strip()
        insecure_keys = {
            "hyperhub_bridge_secret_key_2026",
            "secret",
            "changeme",
            "default_secret",
            "admin",
            "123456",
        }
        if not configured or len(configured) < 16 or configured.lower() in insecure_keys:
            return False
        import hmac
        return hmac.compare_digest(token, configured)

    async def _verify_admin_access(self, request: web.Request) -> dict | None:
        """Xác thực quyền Quản trị viên (4 role Admin, Bot Owner, Guild Owner/Administrator).
        Điều kiện bắt buộc với token Discord OAuth2:
        1. Token hợp lệ (Discord /users/@me)
        2. Email đã xác minh (verified: true) — chống tài khoản rác/spam
        3. Đã vào Discord Server (là guild member)
        4. Có 1 trong 4 role Admin (hoặc là Owner/Administrator)
        Hỗ trợ xác thực qua Authorization Bearer token (Discord OAuth2) hoặc X-Bot-Secret.
        Trả về dict thông tin admin nếu hợp lệ, ngược lại trả về None.
        """
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "X-Bot-Secret" in request.headers:
            token = request.headers["X-Bot-Secret"].strip()

        # 1. Khóa bí mật BOT_API_SECRET luôn có toàn quyền quản trị cao nhất (chỉ chấp nhận secret an toàn)
        if self._is_valid_bot_api_secret(token):
            return {
                "is_admin": True,
                "user_id": BOT_OWNER_ID,
                "username": "Bot Administrator (Secret Key)",
                "display_name": "Administrator",
                "role_name": "👑 Owner",
            }

        if not token:
            return None

        # 2. Xác thực với Discord OAuth2 token
        user_data = await self._verify_discord_bearer_token(token)
        if not user_data:
            return None

        # Bắt buộc email đã xác minh (verified: true) — chặn tài khoản rác/spam bot
        if not user_data.get("verified"):
            logger.warning(f"Từ chối admin: tài khoản {user_data.get('id')} chưa xác minh email")
            return None

        user_id = int(user_data.get("id", 0))

        # Bot Owner luôn có quyền Admin cao nhất
        if user_id == BOT_OWNER_ID or (settings.OWNER_ID and user_id == settings.OWNER_ID):
            return {
                "is_admin": True,
                "user_id": user_id,
                "username": user_data.get("username", "Owner"),
                "display_name": user_data.get("global_name") or user_data.get("username"),
                "role_name": "👑 Owner",
            }

        # Kiểm tra vai trò trong Discord Server
        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return None

        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None

        if not member:
            return None

        # Chủ server hoặc thành viên có quyền administrator
        if guild.owner_id == user_id or member.guild_permissions.administrator:
            return {
                "is_admin": True,
                "user_id": user_id,
                "username": member.name,
                "display_name": member.display_name,
                "role_name": "⚡ Administrator",
            }

        # Kiểm tra 4 role admin theo danh sách yêu cầu
        user_role_ids = {r.id for r in member.roles}
        matched = user_role_ids.intersection(ADMIN_ROLE_IDS)
        if matched:
            top_admin_role = member.top_role.name
            return {
                "is_admin": True,
                "user_id": user_id,
                "username": member.name,
                "display_name": member.display_name,
                "role_name": top_admin_role,
            }

        return None

    async def _admin_deny_reason(self, request: web.Request) -> str:
        """Trả về mã lý do từ chối admin để Web hiển thị gợi ý phù hợp.
        - no_token: chưa liên kết acc Discord / token không hợp lệ
        - unverified: chưa xác minh email Discord
        - not_member: chưa vào Discord Server
        - not_admin: đã vào server nhưng không có role quản trị
        """
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "X-Bot-Secret" in request.headers:
            token = request.headers["X-Bot-Secret"].strip()

        if token and token == settings.BOT_API_SECRET:
            return "secret"
        if not token:
            return "no_token"

        user_data = await self._verify_discord_bearer_token(token)
        if not user_data:
            return "no_token"
        if not user_data.get("verified"):
            return "unverified"

        try:
            user_id = int(user_data.get("id", 0))
        except (ValueError, TypeError):
            return "no_token"

        if user_id == BOT_OWNER_ID or (settings.OWNER_ID and user_id == settings.OWNER_ID):
            return "owner"
        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return "not_member"
        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None
        if not member:
            return "not_member"
        if guild.owner_id == user_id or member.guild_permissions.administrator:
            return "owner"
        if {r.id for r in member.roles}.intersection(ADMIN_ROLE_IDS):
            return "admin"
        return "not_admin"

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler: Any) -> web.Response:
        """Thêm tiêu đề CORS an toàn cho phản hồi."""
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as ex:
                response = ex
            except Exception as e:
                logger.error(f"Internal API error: {e}", exc_info=True)
                # Chống Information Disclosure (CWE-209): Không làm lộ chi tiết mã nguồn / stack trace
                response = web.json_response(
                    {"error": "Internal Server Error", "message": "Lỗi xử lý nội bộ máy chủ."},
                    status=500,
                )

        req_origin = request.headers.get("Origin", "")
        if req_origin:
            response.headers["Access-Control-Allow-Origin"] = req_origin
            response.headers["Vary"] = "Origin"
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD, DELETE, PATCH, PUT"
        
        req_headers = request.headers.get("Access-Control-Request-Headers")
        if req_headers:
            response.headers["Access-Control-Allow-Headers"] = req_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization, X-Bot-Secret, ngrok-skip-browser-warning, cf-skip-browser-warning, Accept, *"
            )
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler: Any) -> web.Response:
        """Kiểm tra token cho các endpoint POST, DELETE, PATCH, PUT / yêu cầu bảo mật."""
        if request.method in ("POST", "DELETE", "PATCH", "PUT"):
            # Endpoint upload, import_gdrive, notify, account/link, study, forum, admin và system endpoints sẽ tự kiểm tra xác thực bên trong handler
            if (
                request.path in ("/api/documents/upload", "/api/documents/import_gdrive", "/api/notify", "/api/account/link", "/api/account/verify-member", "/api/study/checkin")
                or request.path.startswith("/api/study/")
                or request.path.startswith("/api/forum/")
                or request.path.startswith("/api/admin/")
                or request.path.startswith("/api/system/")
            ):
                return await handler(request)

            auth_header = request.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif "X-Bot-Secret" in request.headers:
                token = request.headers["X-Bot-Secret"].strip()

            if not self._is_valid_bot_api_secret(token):
                return web.json_response(
                    {"error": "Unauthorized", "message": "Sai mã khóa bí mật BOT_API_SECRET hoặc khóa không an toàn"},
                    status=401,
                )
        return await handler(request)

    def _setup_routes(self) -> None:
        """Đăng ký các API endpoints."""
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/health", self.handle_health)
        self.app.router.add_get("/api/leaderboard", self.handle_leaderboard)
        self.app.router.add_get("/api/duels/active", self.handle_active_duels)
        self.app.router.add_get("/api/user/{discord_id}", self.handle_user_profile)
        self.app.router.add_post("/api/notify", self.handle_notify)
        self.app.router.add_post("/api/account/link", self.handle_account_link)
        self.app.router.add_post("/api/account/verify-member", self.handle_verify_member)
        self.app.router.add_get("/api/account/me", self.handle_account_me)
        self.app.router.add_get("/api/skills", self.handle_get_skills)
        # Endpoints Diễn Đàn Orbit (Đồng bộ 2 chiều Web <-> Discord #💡・diễn-đàn)
        self.app.router.add_get("/api/forum/threads", self.handle_forum_get_threads)
        self.app.router.add_post("/api/forum/threads", self.handle_forum_create_thread)
        self.app.router.add_get("/api/forum/threads/{thread_id}", self.handle_forum_get_thread_detail)
        self.app.router.add_post("/api/forum/threads/{thread_id}/messages", self.handle_forum_post_message)
        # Endpoints Đồng Bộ Hồ Sơ Học Tập, Chuỗi Ngày Học (Streak) & Bảng Xếp Hạng Học Thuật (Discord <-> Web)
        self.app.router.add_get("/api/study/profile", self.handle_study_profile)
        self.app.router.add_get("/api/study/profile/{discord_id}", self.handle_study_profile)
        self.app.router.add_post("/api/study/checkin", self.handle_study_checkin)
        self.app.router.add_get("/api/study/leaderboard", self.handle_study_leaderboard)
        # Endpoints Kho Tài Liệu & Đề Thi
        self.app.router.add_get("/api/documents", self.handle_get_documents)
        self.app.router.add_get("/api/documents/stats", self.handle_document_stats)
        self.app.router.add_get("/api/documents/request_exam", self.handle_request_exam)
        self.app.router.add_get("/api/documents/random", self.handle_request_exam)
        self.app.router.add_get("/api/documents/{id}/download", self.handle_download_document)
        self.app.router.add_get("/api/documents/{id}/view", self.handle_view_document_inline)
        self.app.router.add_get("/api/documents/{id}/pdf", self.handle_view_document_inline)
        self.app.router.add_get("/api/documents/{id}/file_url", self.handle_get_document_file_url)
        self.app.router.add_get("/api/documents/{id}/content", self.handle_get_document_content)
        self.app.router.add_get("/api/documents/check_hash", self.handle_check_hash)
        self.app.router.add_post("/api/documents/upload", self.handle_upload_document)
        self.app.router.add_post("/api/documents/import_gdrive", self.handle_import_gdrive)
        # Endpoints Admin Portal
        self.app.router.add_get("/api/admin/check", self.handle_admin_check)
        self.app.router.add_get("/api/admin/bans", self.handle_admin_bans)
        self.app.router.add_get("/api/admin/channels", self.handle_admin_channels)
        self.app.router.add_get("/api/admin/members", self.handle_admin_members)
        self.app.router.add_get("/api/admin/logs", self.handle_admin_logs)
        self.app.router.add_get("/api/admin/config", self.handle_admin_config)
        self.app.router.add_get("/api/admin/audit-logs", self.handle_admin_audit_logs)
        self.app.router.add_post("/api/admin/ban", self.handle_admin_ban)
        self.app.router.add_post("/api/admin/unban", self.handle_admin_unban)
        self.app.router.add_post("/api/admin/kick", self.handle_admin_kick)
        self.app.router.add_post("/api/admin/timeout", self.handle_admin_timeout)
        self.app.router.add_delete("/api/admin/documents/{id}", self.handle_admin_delete_document)
        self.app.router.add_patch("/api/admin/documents/{id}", self.handle_admin_edit_document)
        self.app.router.add_post("/api/admin/documents/{id}/archive", self.handle_admin_archive_document)
        self.app.router.add_post("/api/admin/archive/lockdown", self.handle_admin_archive_lockdown)
        self.app.router.add_post("/api/admin/channels", self.handle_admin_create_channel)
        self.app.router.add_post("/api/admin/channels/{id}/lockdown", self.handle_admin_channel_lockdown)
        # Endpoints Đồng Bộ Hệ Thống & Cập Nhật GitHub
        self.app.router.add_get("/api/system/update_status", self.handle_system_update_status)
        self.app.router.add_post("/api/system/check_update", self.handle_system_check_update)
        self.app.router.add_post("/api/system/apply_update", self.handle_system_apply_update)
        self.app.router.add_post("/api/system/reload", self.handle_system_reload)
        self.app.router.add_post("/api/system/announce_startup", self.handle_system_announce_startup)

    async def handle_status(self, request: web.Request) -> web.Response:
        """GET /api/status: Trả về trạng thái hoạt động của Bot."""
        uptime = int(time.time() - START_TIME)
        ping = round(self.bot.latency * 1000, 2) if hasattr(self.bot, "latency") else 0.0

        return web.json_response({
            "status": "online",
            "bot_user": str(self.bot.user) if self.bot.user else "Starting",
            "bot_id": self.bot.user.id if self.bot.user else 0,
            "ping_ms": ping,
            "guilds_count": len(self.bot.guilds),
            "uptime_seconds": uptime,
            "timestamp": int(time.time()),
        })

    async def handle_get_skills(self, request: web.Request) -> web.Response:
        """GET /api/skills: Trả về thông tin hệ sinh thái Agent Skills & Lucian UX/UI 200 elements."""
        skills_dir = os.path.join(os.path.dirname(BOT_BASE_DIR), "Skills")
        lucian_prompt_dir = os.path.join(skills_dir, "lucian-uxui-prompt")
        has_lucian = os.path.isdir(lucian_prompt_dir)

        return web.json_response({
            "status": "ok",
            "skills_root": skills_dir,
            "installed_packages": [
                {
                    "name": "lucian-uxui",
                    "title": "Lucian UX/UI Prompt & CLI",
                    "elements_count": 200,
                    "categories_count": 14,
                    "installed": has_lucian,
                    "repo": "https://github.com/Seokwoooo/lucian-uxui-prompt",
                },
                {
                    "name": "gsap-skills",
                    "title": "GreenSock GSAP Skills",
                    "installed": os.path.isdir(os.path.join(skills_dir, "gsap-skills")),
                    "repo": "https://github.com/greensock/gsap-skills",
                },
                {
                    "name": "agent-skills",
                    "title": "Addy Osmani Agent Skills (UI Engineering & Security)",
                    "installed": os.path.isdir(os.path.join(skills_dir, "agent-skills")),
                    "repo": "https://github.com/addyosmani/agent-skills",
                },
                {
                    "name": "web-quality-skills",
                    "title": "Web Quality & Accessibility (a11y)",
                    "installed": os.path.isdir(os.path.join(skills_dir, "web-quality-skills")),
                    "repo": "https://github.com/addyosmani/web-quality-skills",
                },
            ],
            "total_ecosystem_skills": 9893,
            "timestamp": int(time.time()),
        })

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /api/health: Kiểm tra tình trạng sức khỏe hệ thống (Healthcheck & Telemetry).
        Tuân thủ chuẩn Sentry/FastAPI/DevOps: kiểm tra DB, C++ core, Discord gateway và FTS5.
        """
        start_probe = time.perf_counter()
        health_report: dict[str, Any] = {
            "status": "healthy",
            "timestamp": int(time.time()),
            "uptime_seconds": int(time.time() - START_TIME),
            "services": {},
        }
        all_ok = True

        # 1. Database SQLite health
        db_start = time.perf_counter()
        try:
            if hasattr(self.bot, "db") and self.bot.db:
                row = await self.bot.db.fetchone("SELECT 1")
                db_latency_ms = round((time.perf_counter() - db_start) * 1000, 2)
                health_report["services"]["database"] = {
                    "status": "up" if row and row[0] == 1 else "degraded",
                    "latency_ms": db_latency_ms,
                    "engine": "sqlite_wal_fts5",
                }
            else:
                health_report["services"]["database"] = {
                    "status": "not_initialized",
                    "engine": "sqlite",
                }
        except Exception as e:
            all_ok = False
            health_report["services"]["database"] = {
                "status": "down",
                "error": str(e),
            }

        # 2. C++ Native Core Acceleration
        try:
            from cpp_core.bridge import IS_NATIVE_ACCELERATED, fast_sha256, fast_detect_magic
            test_hash = fast_sha256(b"health")
            test_magic = fast_detect_magic(b"%PDF-1.4")
            health_report["services"]["cpp_core"] = {
                "accelerated": bool(IS_NATIVE_ACCELERATED),
                "status": "native_dll" if IS_NATIVE_ACCELERATED else "python_fallback",
                "sha256": "ok" if len(test_hash) == 64 else "fail",
                "magic_detection": "ok" if test_magic == "PDF" else "fail",
            }
        except Exception as e:
            health_report["services"]["cpp_core"] = {
                "status": "error",
                "error": str(e),
            }

        # 3. Discord Gateway
        try:
            is_ready = self.bot.is_ready() if hasattr(self.bot, "is_ready") else False
            ping = round(self.bot.latency * 1000, 2) if hasattr(self.bot, "latency") else 0.0
            health_report["services"]["discord_gateway"] = {
                "status": "connected" if is_ready else "connecting",
                "ping_ms": ping,
                "guilds": len(self.bot.guilds) if hasattr(self.bot, "guilds") else 0,
            }
        except Exception as e:
            health_report["services"]["discord_gateway"] = {
                "status": "down",
                "error": str(e),
            }

        # 4. FTS5 Index Probe
        try:
            if hasattr(self.bot, "db") and self.bot.db:
                fts_test = await self.bot.db.fetchone(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='documents_fts'"
                )
                health_report["services"]["fts5_search"] = {
                    "available": bool(fts_test and fts_test[0] > 0),
                    "table": "documents_fts",
                }
        except Exception:
            health_report["services"]["fts5_search"] = {"available": False}

        health_report["probe_time_ms"] = round((time.perf_counter() - start_probe) * 1000, 2)
        if not all_ok:
            health_report["status"] = "degraded"
            return web.json_response(health_report, status=503)

        return web.json_response(health_report, status=200)

    async def handle_leaderboard(self, request: web.Request) -> web.Response:
        """GET /api/leaderboard?mode=ranked&limit=50: Lấy bảng xếp hạng."""
        mode = request.query.get("mode", "ranked").lower()
        if mode not in ("ranked", "freedom"):
            mode = "ranked"
        try:
            limit = int(request.query.get("limit", 50))
        except (ValueError, TypeError):
            return web.json_response({"error": "Tham số limit không hợp lệ"}, status=400)
        limit = max(1, min(limit, 100))

        from database.database import async_session_factory
        from database.repositories.user_repo import UserRepository

        async with async_session_factory() as session:
            repo = UserRepository(session)
            if mode == "freedom":
                users, total = await repo.get_leaderboard(page=1, per_page=limit, sort_by="rating")
                data = [
                    {
                        "rank": idx + 1,
                        "discord_id": u.discord_id,
                        "cf_handle": getattr(u, "codeforces_handle", None) or getattr(u, "cf_handle", None) or "",
                        "rating": u.rating,
                        "tier": u.rank,
                    }
                    for idx, u in enumerate(users)
                ]
            else:
                users, total = await repo.get_leaderboard(page=1, per_page=limit, sort_by="ranked")
                data = [
                    {
                        "rank": idx + 1,
                        "discord_id": u.discord_id,
                        "cf_handle": getattr(u, "codeforces_handle", None) or getattr(u, "cf_handle", None) or "",
                        "ranked_rating": u.ranked_rating,
                        "ranked_tier": u.ranked_rank,
                        "ranked_wins": u.ranked_wins,
                        "ranked_losses": u.ranked_losses,
                        "win_rate": round(
                            (u.ranked_wins / max(1, u.ranked_wins + u.ranked_losses)) * 100, 1
                        ),
                    }
                    for idx, u in enumerate(users)
                ]

        return web.json_response({"mode": mode, "total": total, "leaderboard": data})

    async def handle_active_duels(self, request: web.Request) -> web.Response:
        """GET /api/duels/active: Lấy danh sách các trận đấu Ranked 1:1 đang diễn ra."""
        try:
            ranked_cog = self.bot.get_cog("RankedDuelCog")
            sessions = getattr(ranked_cog.matchmaker, "active_sessions", {}) if ranked_cog and hasattr(ranked_cog, "matchmaker") else {}

            active_list = []
            for channel_id, session in sessions.items():
                active_list.append({
                    "channel_id": channel_id,
                    "player1": {
                        "id": getattr(session.player1, "id", 0),
                        "name": getattr(session.player1, "display_name", "P1"),
                        "lives": getattr(session, "p1_lives", 2),
                        "tier": getattr(session, "p1_ranked_rank", "T8"),
                        "rating": getattr(session, "p1_ranked_rating", 0),
                    },
                    "player2": {
                        "id": getattr(session.player2, "id", 0),
                        "name": getattr(session.player2, "display_name", "P2"),
                        "lives": getattr(session, "p2_lives", 2),
                        "tier": getattr(session, "p2_ranked_rank", "T8"),
                        "rating": getattr(session, "p2_ranked_rating", 0),
                    },
                    "round": getattr(session, "current_round", 1),
                    "problem_name": session.current_problem.name if getattr(session, "current_problem", None) else "",
                    "problem_tier": session.current_problem.tier if getattr(session, "current_problem", None) else "",
                })
            return web.json_response({"active_count": len(active_list), "duels": active_list})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_user_profile(self, request: web.Request) -> web.Response:
        """GET /api/user/{discord_id}: Lấy thông tin thống kê người dùng."""
        try:
            discord_id = int(request.match_info["discord_id"])
        except ValueError:
            return web.json_response({"error": "ID người dùng không hợp lệ"}, status=400)

        from database.database import async_session_factory
        from database.repositories.user_repo import UserRepository

        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(discord_id)
            if not user:
                return web.json_response({"error": "Không tìm thấy người dùng"}, status=404)

            return web.json_response({
                "discord_id": user.discord_id,
                "cf_handle": getattr(user, "codeforces_handle", None) or getattr(user, "cf_handle", None) or "",
                "freedom": {
                    "rating": user.rating,
                    "tier": user.rank,
                    "problems_solved": getattr(user, "total_solved", None) or getattr(user, "problems_solved", 0) or 0,
                },
                "ranked": {
                    "rating": user.ranked_rating,
                    "tier": user.ranked_rank,
                    "wins": user.ranked_wins,
                    "losses": user.ranked_losses,
                    "draws": user.ranked_draws,
                },
            })

    async def handle_account_link(self, request: web.Request) -> web.Response:
        """POST /api/account/link: Lưu/cập nhật tài khoản Discord đã liên kết web.
        Xác thực bằng Discord OAuth2 Bearer (KHÔNG bao giờ nhận/lưu access token thô
        ngoài việc verify 1 lần với Discord API)."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        if not token or self._is_valid_bot_api_secret(token):
            return web.json_response({"error": "Yêu cầu Bearer token Discord OAuth2"}, status=401)

        user_data = await self._verify_discord_bearer_token(token)
        if not user_data:
            return web.json_response({"error": "Token Discord không hợp lệ hoặc đã hết hạn"}, status=401)

        try:
            discord_id = int(user_data.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "Dữ liệu Discord không hợp lệ"}, status=400)
        if not discord_id:
            return web.json_response({"error": "Dữ liệu Discord không hợp lệ"}, status=400)

        username = str(user_data.get("username", ""))
        global_name = str(user_data.get("global_name") or username)
        avatar_hash = user_data.get("avatar")
        avatar_url = (
            f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
            if avatar_hash else ""
        )
        email = str(user_data.get("email") or "")
        verified = 1 if user_data.get("verified") else 0
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        await self.bot.db.execute(
            """INSERT INTO linked_accounts
               (discord_id, username, global_name, avatar_url, email, verified, first_seen, last_seen, login_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(discord_id) DO UPDATE SET
                 username=excluded.username, global_name=excluded.global_name,
                 avatar_url=excluded.avatar_url, email=excluded.email, verified=excluded.verified,
                 last_seen=excluded.last_seen, login_count=login_count+1""",
            discord_id, username, global_name, avatar_url, email, verified, now_iso, now_iso,
        )
        return web.json_response({
            "success": True,
            "message": "Đã lưu tài khoản liên kết.",
            "account": {
                "discord_id": discord_id,
                "username": username,
                "verified": bool(verified),
            },
        })

    async def handle_account_me(self, request: web.Request) -> web.Response:
        """GET /api/account/me: Lấy hồ sơ tài khoản đã lưu theo Bearer token hiện tại."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        if not token or self._is_valid_bot_api_secret(token):
            return web.json_response({"error": "Yêu cầu Bearer token Discord OAuth2"}, status=401)

        user_data = await self._verify_discord_bearer_token(token)
        if not user_data:
            return web.json_response({"error": "Token Discord không hợp lệ hoặc đã hết hạn"}, status=401)

        try:
            discord_id = int(user_data.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "Dữ liệu Discord không hợp lệ"}, status=400)

        row = await self.bot.db.fetchone(
            "SELECT discord_id, username, global_name, avatar_url, email, verified, first_seen, last_seen, login_count"
            " FROM linked_accounts WHERE discord_id = ?",
            discord_id,
        )
        if not row:
            return web.json_response({"error": "Tài khoản chưa được lưu", "linked": False}, status=404)
        return web.json_response({
            "success": True,
            "linked": True,
            "account": {
                "discord_id": row[0],
                "username": row[1],
                "global_name": row[2],
                "avatar_url": row[3],
                "email": row[4],
                "verified": bool(row[5]),
                "first_seen": row[6],
                "last_seen": row[7],
                "login_count": row[8],
            },
        })

    async def handle_notify(self, request: web.Request) -> web.Response:
        """POST /api/notify: Cho phép Web gửi tin nhắn vào Discord Channel.
        Chấp nhận 2 hình thức xác thực: BOT_API_SECRET (máy chủ) hoặc
        tài khoản Quản trị viên Discord (Bearer OAuth2, dùng cho Admin Console)."""
        # 1. Ưu tiên khóa bí mật máy chủ
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        secret_ok = self._is_valid_bot_api_secret(token)
        if not secret_ok and "X-Bot-Secret" in request.headers:
            secret_ok = self._is_valid_bot_api_secret(request.headers["X-Bot-Secret"].strip())

        admin_info = None
        if not secret_ok:
            # 2. Fallback: tài khoản Discord phải có quyền Quản trị viên
            admin_info = await self._verify_admin_access(request)
            if not admin_info:
                return web.json_response(
                    {"error": "Unauthorized", "message": "Yêu cầu BOT_API_SECRET hoặc quyền Quản trị viên Discord"},
                    status=401,
                )

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
        try:
            channel_id = int(body.get("channel_id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "channel_id không hợp lệ"}, status=400)
        content = str(body.get("message", ""))
        if not channel_id or not content:
            return web.json_response(
                {"error": "Thiếu channel_id hoặc message"}, status=400
            )
        if channel_id <= 0 or len(content) > 2000:
            return web.json_response({"error": "Dữ liệu gửi tin nhắn không hợp lệ"}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel:
            # Phân biệt nhập nhầm ID Server thay vì ID kênh (lỗi phổ biến)
            guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
            if guild and channel_id == guild.id:
                return web.json_response(
                    {"error": "Đây là ID của Server, không phải ID kênh. Hãy chuột phải vào KÊNH Discord → Sao chép ID kênh (số nằm trong mục Thông Báo của Admin)."},
                    status=400,
                )
            return web.json_response({"error": "Kênh Discord không tồn tại hoặc Bot không thể truy cập kênh này"}, status=404)

        try:
            import discord
            # Vô hiệu hóa triệt để mass mentions (@everyone, @here, role pings) chống lạm dụng spam ping
            await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
            actor = admin_info.get("username") if admin_info else "server"
            logger.info(f"Notify từ Web bởi {actor} tới kênh {channel_id}")
            return web.json_response({"success": True, "channel_id": channel_id})
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo Discord: {e}", exc_info=True)
            return web.json_response(
                {"error": "Không thể gửi tin nhắn thông báo", "message": "Lỗi nội bộ khi gửi tin nhắn tới Discord."},
                status=500,
            )

    async def handle_get_documents(self, request: web.Request) -> web.Response:
        """GET /api/documents: Trả về danh sách tài liệu học tập & đề thi lưu trữ."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

        query_params = request.rel_url.query
        subject = query_params.get("subject", "").strip()
        search_kw = query_params.get("search", "").strip()
        raw_limit = query_params.get("limit", "20").strip().lower()
        try:
            if raw_limit in ("0", "-1", "all", "unlimited"):
                limit = 100000
                page = 1
            else:
                limit = min(max(int(raw_limit), 1), 10000)
                page = max(int(query_params.get("page", 1)), 1)
        except ValueError:
            limit = 20
            page = 1
        offset = (page - 1) * limit

        where_clauses = []
        params = []

        grade = query_params.get("grade", "").strip()
        exam_type = query_params.get("exam_type", "").strip()

        if subject and subject.upper() != "ALL":
            where_clauses.append("LOWER(subject) = LOWER(?)")
            params.append(subject)

        if grade and grade.upper() != "ALL":
            where_clauses.append("(estimated_level LIKE ? OR title LIKE ?)")
            params.extend([f"%{grade}%", f"%{grade}%"])

        if exam_type and exam_type.upper() != "ALL":
            et = exam_type.upper().strip()
            if et == "THUONG":
                where_clauses.append("(LOWER(estimated_level) LIKE '%thuong%' OR LOWER(estimated_level) LIKE '%thường%' OR LOWER(title) LIKE '%thường%' OR LOWER(title) LIKE '%học kỳ%' OR LOWER(title) LIKE '%định kỳ%' OR LOWER(title) LIKE '%thi thử%')")
            elif et == "HSG":
                where_clauses.append("(LOWER(estimated_level) LIKE '%hsg%' OR LOWER(title) LIKE '%hsg%' OR LOWER(title) LIKE '%học sinh giỏi%')")
            elif et == "CHUYEN":
                where_clauses.append("(LOWER(estimated_level) LIKE '%chuyen%' OR LOWER(estimated_level) LIKE '%chuyên%' OR LOWER(title) LIKE '%chuyên%' OR LOWER(title) LIKE '%chuyen%')")
            elif et in ("QUOC_TE", "QUOCTE", "INTERNATIONAL"):
                where_clauses.append("(LOWER(estimated_level) LIKE '%quốc tế%' OR LOWER(estimated_level) LIKE '%quoc te%' OR LOWER(title) LIKE '%quốc tế%' OR LOWER(title) LIKE '%quoc te%' OR LOWER(title) LIKE '%international%' OR LOWER(title) LIKE '%imo%' OR LOWER(title) LIKE '%amc%' OR LOWER(title) LIKE '%kangaroo%' OR LOWER(title) LIKE '%ikmc%' OR LOWER(title) LIKE '%sasmo%' OR LOWER(title) LIKE '%timo%' OR LOWER(title) LIKE '%hkimo%' OR LOWER(title) LIKE '%sat%' OR LOWER(title) LIKE '%cambridge%')")
            elif et in ("CHUNG", "TONG_HOP"):
                where_clauses.append("(LOWER(estimated_level) LIKE '%chung%' OR LOWER(estimated_level) LIKE '%phổ thông chung%' OR LOWER(title) LIKE '%tổng hợp%' OR LOWER(title) LIKE '%đề cương%' OR LOWER(title) LIKE '%lý thuyết%')")
            else:
                where_clauses.append("(file_type LIKE ? OR estimated_level LIKE ? OR title LIKE ?)")
                params.extend([f"%{exam_type}%", f"%{exam_type}%", f"%{exam_type}%"])

        if search_kw:
            fts_words = re.findall(r'[\w\u00C0-\u024F\u1E00-\u1EFF]+', search_kw)
            if fts_words:
                fts_expr = ' '.join(f'"{w}"*' for w in fts_words)
                where_clauses.append(
                    "(id IN (SELECT rowid FROM documents_fts WHERE documents_fts MATCH ?) OR LOWER(title) LIKE ? OR LOWER(file_name) LIKE ?)"
                )
                kw_param = f"%{search_kw.lower()}%"
                params.extend([fts_expr, kw_param, kw_param])
            else:
                where_clauses.append("(LOWER(title) LIKE ? OR LOWER(file_name) LIKE ?)")
                kw_param = f"%{search_kw.lower()}%"
                params.extend([kw_param, kw_param])

        filter_dup = query_params.get("filter_dup", "all").strip().lower()
        if filter_dup == "unique":
            where_clauses.append("id IN (SELECT MIN(id) FROM documents_archive GROUP BY COALESCE(NULLIF(file_hash, ''), LOWER(file_name)))")
        elif filter_dup == "duplicate":
            where_clauses.append("(file_hash IN (SELECT file_hash FROM documents_archive WHERE file_hash IS NOT NULL AND file_hash != '' GROUP BY file_hash HAVING COUNT(*) > 1) OR LOWER(file_name) IN (SELECT LOWER(file_name) FROM documents_archive GROUP BY LOWER(file_name) HAVING COUNT(*) > 1))")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_sql = f"SELECT COUNT(*) FROM documents_archive {where_sql}"
        count_row = await self.bot.db.fetchone(count_sql, *params)
        total = count_row[0] if count_row else 0

        # Map min_id và count cho từng hash / tên file để xác định bản gốc vs bản trùng (Cache 60s)
        now_ts = time.time()
        if self._doc_min_id_cache and now_ts - self._doc_min_id_cache[1] < 60.0:
            doc_stats_map = self._doc_min_id_cache[0]
        else:
            min_id_rows = await self.bot.db.fetchall("""
                SELECT COALESCE(NULLIF(file_hash, ''), LOWER(file_name)), MIN(id), COUNT(*)
                FROM documents_archive
                GROUP BY COALESCE(NULLIF(file_hash, ''), LOWER(file_name))
            """)
            doc_stats_map = {r[0]: (r[1], r[2]) for r in min_id_rows if r[0]}
            self._doc_min_id_cache = (doc_stats_map, now_ts)

        base_cols = (
            "id, subject, title, file_name, file_size_bytes, file_type, estimated_level,"
            "question_count, page_count, author_name, jump_url, timestamp, file_hash, notes"
        )
        scan_cols = "verdict, exam_track, confidence, academic_year, school_or_department"
        try:
            data_sql = f"""
                SELECT {base_cols}, {scan_cols}
                FROM documents_archive
                {where_sql}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            rows = await self.bot.db.fetchall(data_sql, *params, limit, offset)
            has_scan = True
        except Exception:
            # DB cũ chưa migrate đầy đủ các cột mới
            try:
                data_sql = f"""
                    SELECT {base_cols}, verdict, exam_track, confidence
                    FROM documents_archive
                    {where_sql}
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                """
                rows = await self.bot.db.fetchall(data_sql, *params, limit, offset)
                has_scan = True
            except Exception:
                data_sql = f"""
                    SELECT {base_cols}
                    FROM documents_archive
                    {where_sql}
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                """
                rows = await self.bot.db.fetchall(data_sql, *params, limit, offset)
                has_scan = False

        docs = []
        for r in rows:
            h = r[12] if len(r) > 12 else None
            fn = (r[3] or "").lower()
            lookup_key = (h if h else None) or fn
            min_id, count = doc_stats_map.get(lookup_key, (r[0], 1))
            is_dup = count > 1
            is_duplicate_copy = bool(is_dup and r[0] != min_id)

            notes_str = r[13] if len(r) > 13 and r[13] else ""
            ac_year = r[17] if has_scan and len(r) > 17 and r[17] else None
            sch_dept = r[18] if has_scan and len(r) > 18 and r[18] else None

            # Fallback regex bóc tách năm học nếu cột null
            if not ac_year:
                combined_text = f"{r[2] or ''} {notes_str}"
                m_yr = re.search(r'(?:năm\s*học|hk\s*[12]\s*năm)?\s*(20\d{2}\s*[-–—]\s*20\d{2})', combined_text, re.IGNORECASE)
                if m_yr:
                    ac_year = m_yr.group(1).replace(" ", "")

            # Fallback regex bóc tách trường / sở GD nếu cột null
            if not sch_dept and notes_str:
                m_sch = re.search(r'Nguồn:\s*([^|\n]+)', notes_str)
                if m_sch:
                    sch_dept = m_sch.group(1).strip()

            docs.append({
                "id": r[0],
                "subject": r[1],
                "title": r[2],
                "file_name": r[3],
                "file_size_bytes": r[4],
                "file_type": r[5],
                "estimated_level": r[6],
                "question_count": r[7],
                "page_count": r[8],
                "author_name": r[9],
                "jump_url": r[10],
                "timestamp": r[11],
                "file_hash": h,
                "notes": notes_str,
                "verdict": r[14] if has_scan and len(r) > 14 else None,
                "exam_track": r[15] if has_scan and len(r) > 15 else None,
                "confidence": r[16] if has_scan and len(r) > 16 else None,
                "academic_year": ac_year,
                "school_or_department": sch_dept,
                "is_duplicate": is_dup,
                "is_duplicate_copy": is_duplicate_copy,
                "original_id": min_id if is_duplicate_copy else None,
                "duplicate_count": count,
                "download_url": f"/api/documents/{r[0]}/download",
            })

        return web.json_response({
            "success": True,
            "total": total,
            "total_real": total,
            "page": page,
            "limit": limit,
            "documents": docs,
        })

    async def handle_document_stats(self, request: web.Request) -> web.Response:
        """GET /api/documents/stats: Thống kê kho tài liệu (Tổng số thực tế, đề độc bản & đề trùng) có Cache 30s."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

        now_ts = time.time()
        if self._doc_stats_cache and now_ts - self._doc_stats_cache[1] < 30.0:
            return web.json_response(self._doc_stats_cache[0])

        total_row = await self.bot.db.fetchone(
            "SELECT COUNT(*), COALESCE(SUM(file_size_bytes), 0) FROM documents_archive"
        )
        total_items = total_row[0] if total_row else 0
        total_bytes = total_row[1] if total_row else 0

        # Thống kê số lượng đề độc bản (Unique)
        unique_row = await self.bot.db.fetchone(
            "SELECT COUNT(DISTINCT COALESCE(NULLIF(file_hash, ''), LOWER(file_name))) FROM documents_archive"
        )
        unique_items = unique_row[0] if unique_row else total_items

        # Thống kê số lượng đề có bản trùng trong hệ thống
        dup_row = await self.bot.db.fetchone("""
            SELECT COUNT(*) FROM documents_archive
            WHERE file_hash IN (SELECT file_hash FROM documents_archive WHERE file_hash IS NOT NULL AND file_hash != '' GROUP BY file_hash HAVING COUNT(*) > 1)
               OR LOWER(file_name) IN (SELECT LOWER(file_name) FROM documents_archive GROUP BY LOWER(file_name) HAVING COUNT(*) > 1)
        """)
        duplicate_items = dup_row[0] if dup_row else 0

        subject_rows = await self.bot.db.fetchall(
            """
            SELECT subject, COUNT(*), COALESCE(SUM(file_size_bytes), 0)
            FROM documents_archive
            GROUP BY subject
            ORDER BY COUNT(*) DESC
            """
        )
        subjects = [
            {"subject": r[0], "count": r[1], "size_bytes": r[2]}
            for r in subject_rows
        ]

        result_payload = {
            "success": True,
            "total_items": total_items,
            "total_real": total_items,
            "unique_items": unique_items,
            "duplicate_items": duplicate_items,
            "total_bytes": total_bytes,
            "subjects": subjects,
        }
        self._doc_stats_cache = (result_payload, now_ts)
        return web.json_response(result_payload)

    async def handle_request_exam(self, request: web.Request) -> web.Response:
        """GET /api/documents/request_exam: Lấy ngẫu nhiên 1 đề thi theo lớp, loại đề và mô tả."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng", "bot_online": False}, status=503)

        # 1. Rate limiting (Tối đa 30 request / phút / IP)
        client_ip = request.remote or "unknown"
        now = time.time()
        ip_history = [t for t in self._exam_rate_limits.get(client_ip, []) if now - t < 60.0]
        if len(ip_history) >= 30:
            return web.json_response({
                "success": False,
                "error": "Quá nhiều yêu cầu phát đề. Vui lòng thử lại sau 1 phút.",
            }, status=429)
        ip_history.append(now)
        self._exam_rate_limits[client_ip] = ip_history

        # 2. BẮT BUỘC là thành viên Discord Server (kèm email đã xác minh)
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        secret_ok = self._is_valid_bot_api_secret(token)
        if not secret_ok and "X-Bot-Secret" in request.headers:
            secret_ok = self._is_valid_bot_api_secret(request.headers["X-Bot-Secret"].strip())

        if not secret_ok:
            if not token:
                return web.json_response({
                    "success": False,
                    "error": "Chưa liên kết Discord",
                    "message": "Bạn cần liên kết tài khoản Discord để lấy đề thi.",
                    "reason": "no_token",
                }, status=401)
            user_data = await self._verify_discord_bearer_token(token)
            if not user_data:
                return web.json_response({
                    "success": False,
                    "error": "Phiên Discord hết hạn",
                    "message": "Phiên đăng nhập Discord đã hết hạn. Hãy đăng xuất và liên kết lại.",
                    "reason": "no_token",
                }, status=401)
            if not user_data.get("verified", False):
                return web.json_response({
                    "success": False,
                    "error": "Tài khoản Discord chưa xác minh Email",
                    "message": "Tài khoản Discord của bạn chưa xác minh Email (Unverified). Vui lòng xác minh email trên Discord để được cấp quyền nhận phát đề.",
                    "reason": "unverified",
                }, status=403)
            try:
                exam_user_id = int(user_data.get("id", 0))
            except (ValueError, TypeError):
                exam_user_id = 0
            guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
            member = guild.get_member(exam_user_id) if guild and exam_user_id else None
            if member is None and guild and exam_user_id:
                try:
                    member = await guild.fetch_member(exam_user_id)
                except Exception:
                    member = None
            if not member:
                return web.json_response({
                    "success": False,
                    "error": "Chưa tham gia server",
                    "message": "Bạn phải tham gia Discord Server Orbit mới được lấy đề thi.",
                    "reason": "not_member",
                    "guild_id": str(DISCORD_GUILD_ID),
                }, status=403)

        query_params = request.rel_url.query
        grade = query_params.get("grade", "").strip()
        exam_type = query_params.get("exam_type", "").strip()
        subject = query_params.get("subject", "").strip()
        desc = query_params.get("description", "").strip()

        where_clauses = []
        params = []

        if subject and subject.upper() != "ALL":
            where_clauses.append("LOWER(subject) = LOWER(?)")
            params.append(subject)

        if grade and grade.upper() != "ALL":
            where_clauses.append("(estimated_level LIKE ? OR title LIKE ?)")
            params.extend([f"%{grade}%", f"%{grade}%"])

        if exam_type and exam_type.upper() != "ALL":
            et = exam_type.upper().strip()
            if et == "THUONG":
                where_clauses.append("(LOWER(estimated_level) LIKE '%thuong%' OR LOWER(estimated_level) LIKE '%thường%' OR LOWER(title) LIKE '%thường%' OR LOWER(title) LIKE '%học kỳ%' OR LOWER(title) LIKE '%định kỳ%' OR LOWER(title) LIKE '%thi thử%')")
            elif et == "HSG":
                where_clauses.append("(LOWER(estimated_level) LIKE '%hsg%' OR LOWER(title) LIKE '%hsg%' OR LOWER(title) LIKE '%học sinh giỏi%')")
            elif et == "CHUYEN":
                where_clauses.append("(LOWER(estimated_level) LIKE '%chuyen%' OR LOWER(estimated_level) LIKE '%chuyên%' OR LOWER(title) LIKE '%chuyên%' OR LOWER(title) LIKE '%chuyen%')")
            elif et in ("QUOC_TE", "QUOCTE", "INTERNATIONAL"):
                where_clauses.append("(LOWER(estimated_level) LIKE '%quốc tế%' OR LOWER(estimated_level) LIKE '%quoc te%' OR LOWER(title) LIKE '%quốc tế%' OR LOWER(title) LIKE '%quoc te%' OR LOWER(title) LIKE '%international%' OR LOWER(title) LIKE '%imo%' OR LOWER(title) LIKE '%amc%' OR LOWER(title) LIKE '%kangaroo%' OR LOWER(title) LIKE '%ikmc%' OR LOWER(title) LIKE '%sasmo%' OR LOWER(title) LIKE '%timo%' OR LOWER(title) LIKE '%hkimo%' OR LOWER(title) LIKE '%sat%' OR LOWER(title) LIKE '%cambridge%')")
            elif et in ("CHUNG", "TONG_HOP"):
                where_clauses.append("(LOWER(estimated_level) LIKE '%chung%' OR LOWER(estimated_level) LIKE '%phổ thông chung%' OR LOWER(title) LIKE '%tổng hợp%' OR LOWER(title) LIKE '%đề cương%' OR LOWER(title) LIKE '%lý thuyết%')")
            else:
                where_clauses.append("(file_type LIKE ? OR estimated_level LIKE ? OR title LIKE ?)")
                params.extend([f"%{exam_type}%", f"%{exam_type}%", f"%{exam_type}%"])

        if desc:
            where_clauses.append("(LOWER(title) LIKE ? OR LOWER(file_name) LIKE ?)")
            desc_param = f"%{desc.lower()}%"
            params.extend([desc_param, desc_param])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        try:
            sql = f"""
                SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level,
                       question_count, page_count, author_name, jump_url, timestamp, file_hash, notes,
                       verdict, exam_track, confidence, academic_year, school_or_department
                FROM documents_archive
                {where_sql}
                ORDER BY RANDOM()
                LIMIT 1
            """
            row = await self.bot.db.fetchone(sql, *params)
            has_scan = True
        except Exception:
            try:
                sql = f"""
                    SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level,
                           question_count, page_count, author_name, jump_url, timestamp, file_hash, notes,
                           verdict, exam_track, confidence
                    FROM documents_archive
                    {where_sql}
                    ORDER BY RANDOM()
                    LIMIT 1
                """
                row = await self.bot.db.fetchone(sql, *params)
                has_scan = True
            except Exception:
                sql = f"""
                    SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level,
                           question_count, page_count, author_name, jump_url, timestamp, file_hash, notes
                    FROM documents_archive
                    {where_sql}
                    ORDER BY RANDOM()
                    LIMIT 1
                """
                row = await self.bot.db.fetchone(sql, *params)
                has_scan = False

        # Fallback nếu không có đề nào khớp 100% tất cả tiêu chí cùng lúc
        is_fallback = False
        if not row and where_clauses:
            is_fallback = True
            # Thử tìm theo lớp hoặc môn
            fb_clauses = []
            fb_params = []
            if grade and grade.upper() != "ALL":
                fb_clauses.append("(estimated_level LIKE ? OR title LIKE ?)")
                fb_params.extend([f"%{grade}%", f"%{grade}%"])
            elif subject and subject.upper() != "ALL":
                fb_clauses.append("LOWER(subject) = LOWER(?)")
                fb_params.append(subject)

            if fb_clauses:
                fb_where = "WHERE " + " AND ".join(fb_clauses)
                try:
                    row = await self.bot.db.fetchone(
                        f"SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes, verdict, exam_track, confidence, academic_year, school_or_department FROM documents_archive {fb_where} ORDER BY RANDOM() LIMIT 1",
                        *fb_params,
                    )
                    has_scan = True
                except Exception:
                    try:
                        row = await self.bot.db.fetchone(
                            f"SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes, verdict, exam_track, confidence FROM documents_archive {fb_where} ORDER BY RANDOM() LIMIT 1",
                            *fb_params,
                        )
                        has_scan = True
                    except Exception:
                        row = await self.bot.db.fetchone(
                            f"SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes FROM documents_archive {fb_where} ORDER BY RANDOM() LIMIT 1",
                            *fb_params,
                        )
                        has_scan = False

            # Nếu vẫn chưa có, lấy ngẫu nhiên 1 đề bất kỳ trong kho
            if not row:
                try:
                    row = await self.bot.db.fetchone(
                        "SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes, verdict, exam_track, confidence, academic_year, school_or_department FROM documents_archive ORDER BY RANDOM() LIMIT 1"
                    )
                    has_scan = True
                except Exception:
                    try:
                        row = await self.bot.db.fetchone(
                            "SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes, verdict, exam_track, confidence FROM documents_archive ORDER BY RANDOM() LIMIT 1"
                        )
                        has_scan = True
                    except Exception:
                        row = await self.bot.db.fetchone(
                            "SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, jump_url, timestamp, file_hash, notes FROM documents_archive ORDER BY RANDOM() LIMIT 1"
                        )
                        has_scan = False
        else:
            has_scan = False

        if not row:
            return web.json_response({"success": False, "message": "Hiện chưa có đề thi nào trong kho lưu trữ."})

        notes_str = row[13] if len(row) > 13 and row[13] else ""
        ac_year = row[17] if has_scan and len(row) > 17 and row[17] else None
        sch_dept = row[18] if has_scan and len(row) > 18 and row[18] else None

        # Fallback regex bóc tách năm học nếu cột null
        if not ac_year:
            combined_text = f"{row[2] or ''} {notes_str}"
            m_yr = re.search(r'(?:năm\s*học|hk\s*[12]\s*năm)?\s*(20\d{2}\s*[-–—]\s*20\d{2})', combined_text, re.IGNORECASE)
            if m_yr:
                ac_year = m_yr.group(1).replace(" ", "")

        # Fallback regex bóc tách trường / sở GD nếu cột null
        if not sch_dept and notes_str:
            m_sch = re.search(r'Nguồn:\s*([^|\n]+)', notes_str)
            if m_sch:
                sch_dept = m_sch.group(1).strip()

        return web.json_response({
            "success": True,
            "bot_online": True,
            "is_exact_match": not is_fallback,
            "document": {
                "id": row[0],
                "subject": row[1],
                "title": row[2],
                "file_name": row[3],
                "file_size_bytes": row[4],
                "file_type": row[5],
                "estimated_level": row[6],
                "question_count": row[7],
                "page_count": row[8],
                "author_name": row[9],
                "jump_url": row[10],
                "timestamp": row[11],
                "file_hash": row[12] if len(row) > 12 else None,
                "notes": notes_str,
                "verdict": row[14] if has_scan and len(row) > 14 else None,
                "exam_track": row[15] if has_scan and len(row) > 15 else None,
                "confidence": row[16] if has_scan and len(row) > 16 else None,
                "academic_year": ac_year,
                "school_or_department": sch_dept,
                "download_url": f"/api/documents/{row[0]}/download",
            },
        })

    async def handle_download_document(self, request: web.Request) -> web.StreamResponse:
        """GET /api/documents/{id}/download: Chuyển hướng hoặc tải trực tiếp file đề thi về máy."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        try:
            doc_id = int(request.match_info.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        row = await self.bot.db.fetchone(
            "SELECT file_name, channel_id, message_id, jump_url, file_size_bytes, is_chunked FROM documents_archive WHERE id = ?",
            doc_id,
        )
        if not row:
            return web.json_response({"error": "Không tìm thấy đề thi này trong kho"}, status=404)

        file_name = row[0] or "de_thi.pdf"
        channel_id = row[1]
        message_id = row[2]
        jump_url = row[3]

        # 0. File đã offload dạng chunks: tải các phần và ghép lại (0MB local)
        try:
            _is_chunked = bool(row[5]) if len(row) > 5 else False
        except Exception:
            _is_chunked = False
        if _is_chunked:
            try:
                from services.chunk_archive import fetch_merged_bytes
                merged, merge_err = await fetch_merged_bytes(self.bot, self.bot.db, doc_id)
            except Exception as e:
                merged, merge_err = None, f"Lỗi ghép file: {e}"
            if merged:
                safe_dl = os.path.basename(file_name).replace("..", "").strip() or "de_thi.pdf"
                return web.Response(
                    body=merged,
                    content_type="application/octet-stream",
                    headers={
                        "Content-Disposition": f'attachment; filename="{safe_dl}"',
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "private, max-age=3600",
                    },
                )
            logger.warning(f"Không ghép được chunks đề #{doc_id}: {merge_err}; thử các nguồn khác.")

        download_url = None

        # 1. Thử lấy attachment URL trực tiếp từ tin nhắn Discord
        if channel_id and message_id:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))
                if channel:
                    msg = await channel.fetch_message(int(message_id))
                    for att in msg.attachments:
                        if att.filename == file_name or att.filename.lower() == file_name.lower():
                            download_url = att.url
                            break
                    if not download_url and msg.attachments:
                        download_url = msg.attachments[0].url
            except Exception as e:
                logger.warning(f"Không thể lấy attachment từ Discord: {e}")

        # 2. Thử lấy từ thư mục uploads local nếu là file người dùng nộp qua Web
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        safe_file_name = os.path.basename(file_name).replace("..", "").strip()
        local_file = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{safe_file_name}"))
        real_upload_dir = os.path.realpath(upload_dir)

        # Ngăn chặn triệt để Path Traversal (CWE-22) và ép tải về tệp (chống XSS inline)
        if local_file.startswith(real_upload_dir + os.sep) and os.path.exists(local_file):
            return web.FileResponse(
                local_file,
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_file_name}"',
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "private, max-age=3600",
                },
            )

        # 3. Nếu có download_url (Discord CDN), chuyển tiếp trực tiếp (Redirect 302) để tải ngay
        if download_url:
            raise web.HTTPFound(download_url)

        # 4. Fallback: Nếu có jump_url
        if jump_url:
            raise web.HTTPFound(jump_url)

        return web.json_response({"error": "Không tìm thấy liên kết tải cho tệp này"}, status=404)

    async def handle_get_document_file_url(self, request: web.Request) -> web.Response:
        """GET /api/documents/{id}/file_url: Trả về link trực tiếp (Discord CDN) kèm thông tin để Web xem trước (PDF/DOCX Preview)."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        try:
            doc_id = int(request.match_info.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        row = await self.bot.db.fetchone(
            "SELECT file_name, channel_id, message_id, jump_url, file_size_bytes, file_type, title, subject, estimated_level FROM documents_archive WHERE id = ?",
            doc_id,
        )
        if not row:
            return web.json_response({"error": "Không tìm thấy đề thi này trong kho"}, status=404)

        file_name = row[0] or "de_thi.pdf"
        channel_id = row[1]
        message_id = row[2]
        jump_url = row[3]
        file_size = row[4] or 0
        file_type = (row[5] or "PDF").upper()
        title = row[6] or file_name
        subject = row[7] or "GENERAL"
        grade = row[8] or "ALL"

        direct_url = None

        # Nếu channel_id hoặc message_id thiếu nhưng jump_url có dạng https://discord.com/channels/{guild}/{channel}/{message}
        if (not channel_id or not message_id) and jump_url and "discord.com/channels/" in jump_url:
            m_jump = re.search(r"discord\.com/channels/\d+/(\d+)/(\d+)", jump_url)
            if m_jump:
                channel_id = int(m_jump.group(1))
                message_id = int(m_jump.group(2))

        if channel_id and message_id:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))
                if channel:
                    msg = await channel.fetch_message(int(message_id))
                    for att in msg.attachments:
                        if att.filename == file_name or att.filename.lower() == file_name.lower():
                            direct_url = att.url
                            break
                    if not direct_url and msg.attachments:
                        direct_url = msg.attachments[0].url
            except Exception as e:
                logger.warning(f"Không thể lấy attachment từ Discord: {e}")

        # Lưu direct_url (signed Discord CDN URL) lên Turso bot_kv_store để Vercel Serverless tự stream không tốn băng thông máy nhà
        if direct_url and direct_url.startswith("http"):
            try:
                import json as _json
                from database.turso_client import turso_db
                if turso_db.is_configured:
                    await turso_db.execute(
                        """INSERT INTO bot_kv_store (key, value, updated_at) VALUES (?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                        f"doc_cdn_{doc_id}",
                        _json.dumps({"direct_url": direct_url, "file_name": file_name, "file_type": file_type}, ensure_ascii=False),
                        int(time.time()),
                    )
            except Exception:
                pass

        # Thử lấy file từ local nếu nộp từ web
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        safe_file_name = os.path.basename(file_name).replace("..", "").strip()
        local_file = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{safe_file_name}"))
        real_upload_dir = os.path.realpath(upload_dir)
        if not direct_url and local_file.startswith(real_upload_dir + os.sep) and os.path.exists(local_file):
            direct_url = f"/api/documents/{doc_id}/download"
            # Nếu file local <= 3.5MB, đồng bộ base64 lên Turso để Vercel tự phục vụ
            try:
                fsize = os.path.getsize(local_file)
                if 0 < fsize <= int(3.5 * 1024 * 1024):
                    import base64 as _b64
                    from database.turso_client import turso_db
                    if turso_db.is_configured:
                        with open(local_file, "rb") as lf:
                            b64_str = _b64.b64encode(lf.read()).decode("ascii")
                        await turso_db.execute(
                            "UPDATE documents_archive SET file_content_base64 = ? WHERE id = ? AND (file_content_base64 IS NULL OR file_content_base64 = '')",
                            b64_str,
                            doc_id,
                        )
            except Exception:
                pass

        if not direct_url and jump_url:
            direct_url = jump_url

        return web.json_response({
            "success": True,
            "id": doc_id,
            "title": title,
            "file_name": file_name,
            "file_type": file_type,
            "file_size_bytes": file_size,
            "subject": subject,
            "estimated_level": grade,
            "direct_url": direct_url,
            "download_url": f"/api/documents/{doc_id}/download",
            "view_url": f"/api/documents/{doc_id}/view",
            "jump_url": jump_url,
        })

    async def _fetch_document_raw_bytes(self, doc_id: int) -> tuple[bytes | None, str, str]:
        """Lấy dữ liệu nhị phân (bytes) của tài liệu từ RAM cache, ổ đĩa, chunk archive hoặc Discord attachment."""
        if not hasattr(self, "_inline_doc_cache"):
            self._inline_doc_cache: dict[int, tuple[bytes, str, str, float]] = {}

        now = time.time()
        cached = self._inline_doc_cache.get(doc_id)
        if cached and (now - cached[3] < 1800.0):
            return cached[0], cached[1], cached[2]

        if not hasattr(self.bot, "db") or not self.bot.db:
            return None, "de_thi.pdf", "PDF"

        row = await self.bot.db.fetchone(
            "SELECT file_name, channel_id, message_id, file_type, is_chunked FROM documents_archive WHERE id = ?",
            doc_id,
        )
        if not row:
            return None, "de_thi.pdf", "PDF"

        file_name = row[0] or f"de_thi_{doc_id}.pdf"
        channel_id = row[1]
        message_id = row[2]
        file_type = (row[3] or "PDF").upper()
        is_chunked = bool(row[4]) if len(row) > 4 else False

        raw_bytes: bytes | None = None

        # 1. Kiểm tra file local trong storage/uploads
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        safe_file_name = os.path.basename(file_name).replace("..", "").strip()
        local_file = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{safe_file_name}"))
        real_upload_dir = os.path.realpath(upload_dir)
        if local_file.startswith(real_upload_dir + os.sep) and os.path.exists(local_file):
            try:
                with open(local_file, "rb") as f:
                    raw_bytes = f.read()
            except Exception as e:
                logger.warning(f"Lỗi đọc file local {local_file}: {e}")

        # 2. Nếu là file chunked
        if raw_bytes is None and is_chunked:
            try:
                from services.chunk_archive import fetch_merged_bytes
                merged, _ = await fetch_merged_bytes(self.bot, self.bot.db, doc_id)
                if merged:
                    raw_bytes = merged
            except Exception as e:
                logger.warning(f"Lỗi ghép chunk đề #{doc_id}: {e}")

        # 3. Tải trực tiếp từ Discord attachment (tự động làm mới signed CDN URL)
        if raw_bytes is None and channel_id and message_id:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))
                if channel:
                    msg = await channel.fetch_message(int(message_id))
                    target_att = None
                    for att in msg.attachments:
                        if att.filename == file_name or att.filename.lower() == file_name.lower():
                            target_att = att
                            break
                    if not target_att and msg.attachments:
                        target_att = msg.attachments[0]
                    if target_att:
                        raw_bytes = await target_att.read()
            except Exception as e:
                logger.warning(f"Không thể đọc attachment Discord cho đề #{doc_id}: {e}")

        # Lưu vào LRU RAM cache nếu kích thước <= 12MB (giữ tối đa 6 file trong RAM)
        if raw_bytes is not None and len(raw_bytes) <= 12 * 1024 * 1024:
            if len(self._inline_doc_cache) >= 6:
                oldest_key = min(self._inline_doc_cache.keys(), key=lambda k: self._inline_doc_cache[k][3])
                self._inline_doc_cache.pop(oldest_key, None)
            self._inline_doc_cache[doc_id] = (raw_bytes, file_name, file_type, now)

        return raw_bytes, file_name, file_type

    async def handle_view_document_inline(self, request: web.Request) -> web.StreamResponse:
        """GET /api/documents/{id}/view (hoặc /pdf): Proxy stream trực tiếp PDF/tài liệu ở chế độ inline (hiển thị ngay trong iframe/canvas trên Web)."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        try:
            doc_id = int(request.match_info.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        raw_bytes, file_name, file_type = await self._fetch_document_raw_bytes(doc_id)
        if not raw_bytes:
            # Fallback redirect sang download nếu không lấy được bytes
            return await self.handle_download_document(request)

        ext = os.path.splitext(file_name.lower())[1]
        if raw_bytes[:5] == b"%PDF-" or ext == ".pdf" or file_type == "PDF":
            content_type = "application/pdf"
        elif ext == ".png":
            content_type = "image/png"
        elif ext in (".jpg", ".jpeg"):
            content_type = "image/jpeg"
        elif ext == ".txt":
            content_type = "text/plain; charset=utf-8"
        else:
            content_type = "application/octet-stream"

        safe_ascii = re.sub(r'[^a-zA-Z0-9._-]', '_', file_name) or f"exam_{doc_id}.pdf"
        return web.Response(
            body=raw_bytes,
            content_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_ascii}"',
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @staticmethod
    def _parse_questions_and_keys(raw_text: str) -> dict[str, Any]:
        """Bóc tách danh sách câu hỏi trắc nghiệm / đúng sai / trả lời ngắn và bảng đáp án từ văn bản đề thi."""
        if not raw_text or not raw_text.strip():
            return {"questions": [], "answer_keys": {}, "sections": []}

        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        # 1. Dò tìm bảng đáp án ở cuối đề (VD: 1.A 2.B 3.C hoặc 1-A, 2-D)
        answer_keys: dict[str, str] = {}
        tail_text = text[int(len(text) * 0.55):] if len(text) > 600 else text
        for m in re.finditer(r'\b(\d{1,3})\s*[.:\-–)\s]\s*([A-D])\b', tail_text):
            q_num = m.group(1)
            ans = m.group(2).upper()
            if 1 <= int(q_num) <= 120:
                answer_keys[q_num] = ans

        # 2. Tách các câu hỏi theo mẫu "Câu 1:", "Câu 1.", "Question 1:"
        q_pattern = re.compile(
            r'(?m)^\s*(?:Câu|Cau|Question|Bài|Bai)\s+(\d{1,3})\s*[.:)\-–]?\s*(.*?)(?=^\s*(?:Câu|Cau|Question|Bài|Bai)\s+\d{1,3}\s*[.:)\-–]?|\Z)',
            re.DOTALL | re.IGNORECASE,
        )
        questions = []
        seen_nums = set()
        for match in q_pattern.finditer(text):
            q_num_str = match.group(1)
            body = match.group(2).strip()
            if not body or len(body) < 4:
                continue
            # Tránh nhận nhầm bảng đáp án ở cuối làm câu hỏi trùng số
            if q_num_str in seen_nums and len(body) < 35:
                continue
            seen_nums.add(q_num_str)

            # Bóc tách 4 phương án A, B, C, D nếu có
            options: list[dict[str, str]] = []
            opt_matches = list(re.finditer(r'(?:^|\s|\n)([A-D])\s*[.)]\s+([^\n]+)', body))
            stem = body
            if len(opt_matches) >= 2:
                first_pos = opt_matches[0].start()
                stem = body[:first_pos].strip()
                for idx, om in enumerate(opt_matches[:4]):
                    letter = om.group(1).upper()
                    opt_text = om.group(2).strip()
                    options.append({"key": letter, "text": opt_text})

            # Kiểm tra câu Đúng/Sai (a), b), c), d))
            statements: list[dict[str, str]] = []
            if not options:
                stmt_matches = list(re.finditer(r'(?:^|\n)\s*([a-d])\)\s+([^\n]+)', body))
                if len(stmt_matches) >= 2:
                    first_s = stmt_matches[0].start()
                    stem = body[:first_s].strip()
                    for sm in stmt_matches[:4]:
                        statements.append({"key": sm.group(1).lower(), "text": sm.group(2).strip()})

            q_type = "mcq" if options else ("true_false" if statements else "short_or_essay")
            questions.append({
                "number": int(q_num_str),
                "label": f"Câu {q_num_str}",
                "type": q_type,
                "stem": stem[:1500],
                "options": options,
                "statements": statements,
                "answer_key": answer_keys.get(q_num_str),
            })
            if len(questions) >= 80:
                break

        return {
            "questions": questions,
            "answer_keys": answer_keys,
        }

    async def handle_get_document_content(self, request: web.Request) -> web.Response:
        """GET /api/documents/{id}/content: Trả về nội dung văn bản đề thi, danh sách câu hỏi bóc tách & đáp án để đọc và làm bài trực tiếp trên Web."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        try:
            doc_id = int(request.match_info.get("id", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        row = await self.bot.db.fetchone(
            """
            SELECT id, subject, title, file_name, file_size_bytes, file_type,
                   estimated_level, question_count, page_count, raw_text, notes,
                   academic_year, school_or_department
            FROM documents_archive
            WHERE id = ?
            """,
            doc_id,
        )
        if not row:
            return web.json_response({"error": "Không tìm thấy đề thi này trong kho"}, status=404)

        file_name = row[3] or f"de_thi_{doc_id}.pdf"
        file_type = (row[5] or "PDF").upper()
        raw_text = (row[9] or "").strip()
        notes = row[10] or ""
        page_count = row[8] or 1
        question_count = row[7] or 0

        # Nếu raw_text chưa được lưu trong DB, tự động trích xuất từ tệp gốc (PDF/DOCX/TXT) ngay lập tức
        if len(raw_text) < 60:
            raw_bytes, _, _ = await self._fetch_document_raw_bytes(doc_id)
            if raw_bytes:
                extracted_str = ""
                ext = os.path.splitext(file_name.lower())[1]
                try:
                    if raw_bytes[:5] == b"%PDF-" or ext == ".pdf" or file_type == "PDF":
                        import fitz
                        def _extract_pdf(b: bytes) -> tuple[str, int]:
                            doc_pdf = fitz.open(stream=b, filetype="pdf")
                            pages_txt = []
                            for idx, p in enumerate(doc_pdf):
                                pages_txt.append(f"--- TRANG {idx + 1} ---\n" + p.get_text("text"))
                            cnt = len(doc_pdf)
                            doc_pdf.close()
                            return "\n\n".join(pages_txt).strip(), cnt
                        extracted_str, p_cnt = await asyncio.to_thread(_extract_pdf, raw_bytes)
                        if p_cnt > 0:
                            page_count = p_cnt
                    elif ext == ".docx" or "DOC" in file_type:
                        import io
                        from docx import Document as DocxDocument
                        def _extract_docx(b: bytes) -> str:
                            d = DocxDocument(io.BytesIO(b))
                            paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
                            for tbl in d.tables:
                                for r_tbl in tbl.rows:
                                    row_txt = " | ".join(c.text.strip() for c in r_tbl.cells if c.text.strip())
                                    if row_txt:
                                        paras.append(row_txt)
                            return "\n".join(paras).strip()
                        extracted_str = await asyncio.to_thread(_extract_docx, raw_bytes)
                    elif ext == ".txt" or "TXT" in file_type:
                        extracted_str = raw_bytes.decode("utf-8", errors="replace").strip()
                except Exception as ex_err:
                    logger.warning(f"Lỗi trích xuất văn bản đề #{doc_id}: {ex_err}")

                if extracted_str and len(extracted_str) > len(raw_text):
                    raw_text = extracted_str[:65000]
                    try:
                        await self.bot.db.execute(
                            "UPDATE documents_archive SET raw_text = ?, page_count = ? WHERE id = ?",
                            raw_text, page_count, doc_id,
                        )
                    except Exception:
                        pass
                    try:
                        from database.turso_client import turso_db
                        if turso_db.is_configured:
                            await turso_db.execute(
                                "UPDATE documents_archive SET raw_text = ?, page_count = ? WHERE id = ?",
                                raw_text, page_count, doc_id,
                            )
                    except Exception:
                        pass

        parsed = self._parse_questions_and_keys(raw_text)
        ext = os.path.splitext(file_name.lower())[1]
        is_pdf = ext == ".pdf" or file_type == "PDF"

        return web.json_response({
            "success": True,
            "id": doc_id,
            "subject": row[1],
            "title": row[2] or file_name,
            "file_name": file_name,
            "file_size_bytes": row[4] or 0,
            "file_type": file_type,
            "is_pdf": is_pdf,
            "estimated_level": row[6],
            "question_count": max(question_count, len(parsed["questions"])),
            "page_count": page_count,
            "academic_year": row[11],
            "school_or_department": row[12],
            "raw_text": raw_text,
            "notes": notes,
            "questions": parsed["questions"],
            "answer_keys": parsed["answer_keys"],
            "view_url": f"/api/documents/{doc_id}/view",
            "download_url": f"/api/documents/{doc_id}/download",
        })

    # =========================================================================
    # PHASE 1: ĐỒNG BỘ HỒ SƠ HỌC TẬP, CHUỖI NGÀY HỌC (STREAK) & BẢNG XẾP HẠNG
    # =========================================================================
    @staticmethod
    def _get_vn_today_str() -> tuple[str, str]:
        """Trả về (today_str, yesterday_str) theo múi giờ Việt Nam (UTC+7) định dạng YYYY-MM-DD."""
        vn_tz = datetime.timezone(datetime.timedelta(hours=7))
        now_vn = datetime.datetime.now(vn_tz)
        today_str = now_vn.strftime("%Y-%m-%d")
        yesterday_str = (now_vn - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        return today_str, yesterday_str

    @staticmethod
    def _compute_study_rank(xp: int, streak: int) -> dict[str, Any]:
        """Tính cấp bậc Học thuật (Level & Danh hiệu) dựa trên XP và Streak."""
        xp = max(0, int(xp or 0))
        if xp >= 3000:
            return {"level": 6, "title": "🌌 Huyền Thoại Orbit", "next_xp": 5000, "progress": min(100, int((xp - 3000) / 20))}
        if xp >= 1500:
            return {"level": 5, "title": "👑 Thủ Khoa Khối", "next_xp": 3000, "progress": int(((xp - 1500) / 1500) * 100)}
        if xp >= 700:
            return {"level": 4, "title": "🏅 Học Giả Tinh Anh", "next_xp": 1500, "progress": int(((xp - 700) / 800) * 100)}
        if xp >= 300:
            return {"level": 3, "title": "⚡ Chiến Binh Luyện Đề", "next_xp": 700, "progress": int(((xp - 300) / 400) * 100)}
        if xp >= 100:
            return {"level": 2, "title": "📘 Học Viên Chăm Chỉ", "next_xp": 300, "progress": int(((xp - 100) / 200) * 100)}
        return {"level": 1, "title": "🌱 Tân Binh Orbit", "next_xp": 100, "progress": int((xp / 100) * 100)}

    async def handle_study_profile(self, request: web.Request) -> web.Response:
        """GET /api/study/profile hoặc /api/study/profile/{discord_id}: Lấy hồ sơ học tập, chuỗi ngày học (Streak) & XP đồng bộ Discord <-> Web."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

        discord_id = 0
        raw_id = request.match_info.get("discord_id") or request.query.get("discord_id", "")
        if raw_id:
            try:
                discord_id = int(raw_id)
            except (ValueError, TypeError):
                discord_id = 0

        user_meta: dict[str, Any] = {}
        if not discord_id:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
            if token and not self._is_valid_bot_api_secret(token):
                verified_user = await self._verify_discord_bearer_token(token)
                if verified_user:
                    try:
                        discord_id = int(verified_user.get("id", 0))
                        user_meta = verified_user
                    except (ValueError, TypeError):
                        discord_id = 0

        if not discord_id:
            return web.json_response({"error": "Thiếu discord_id hoặc Bearer token"}, status=400)

        today_str, yesterday_str = self._get_vn_today_str()

        # Đếm số đề đã đóng góp thực tế của người dùng trong kho
        contrib_row = await self.bot.db.fetchone(
            "SELECT COUNT(*) FROM documents_archive WHERE author_id = ?",
            discord_id,
        )
        real_contributed = contrib_row[0] if contrib_row else 0

        row = await self.bot.db.fetchone(
            """
            SELECT discord_id, username, display_name, avatar_url,
                   current_streak, max_streak, last_study_date, study_xp,
                   pomodoro_count, study_minutes, exams_completed, docs_contributed,
                   dream_school, dream_score, updated_at
            FROM study_profiles
            WHERE discord_id = ?
            """,
            discord_id,
        )

        if not row:
            # Kiểm tra thông tin từ linked_accounts hoặc Discord guild member
            acc_row = await self.bot.db.fetchone(
                "SELECT username, global_name, avatar_url FROM linked_accounts WHERE discord_id = ?",
                discord_id,
            )
            uname = (acc_row[0] if acc_row else None) or user_meta.get("username") or f"user_{discord_id}"
            dname = (acc_row[1] if acc_row else None) or user_meta.get("global_name") or uname
            avatar = (acc_row[2] if acc_row else None) or ""
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            init_xp = real_contributed * 50
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO study_profiles
                (discord_id, username, display_name, avatar_url, current_streak, max_streak,
                 last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
                 docs_contributed, dream_school, dream_score, updated_at)
                VALUES (?, ?, ?, ?, 0, 0, '', ?, 0, 0, 0, ?, '', '', ?)
                """,
                discord_id, uname, dname, avatar, init_xp, real_contributed, now_iso,
            )
            row = await self.bot.db.fetchone(
                """
                SELECT discord_id, username, display_name, avatar_url,
                       current_streak, max_streak, last_study_date, study_xp,
                       pomodoro_count, study_minutes, exams_completed, docs_contributed,
                       dream_school, dream_score, updated_at
                FROM study_profiles
                WHERE discord_id = ?
                """,
                discord_id,
            )

        current_streak = row[4] or 0
        max_streak = row[5] or 0
        last_date = row[6] or ""
        # Nếu nghỉ quá 1 ngày (last_date < yesterday_str), hiển thị streak thực tế là 0 (nhưng giữ max_streak)
        active_streak = current_streak if last_date in (today_str, yesterday_str) else 0
        checked_in_today = (last_date == today_str)
        docs_contributed = max(row[11] or 0, real_contributed)
        study_xp = max(row[7] or 0, docs_contributed * 50)
        rank_info = self._compute_study_rank(study_xp, active_streak)

        return web.json_response({
            "success": True,
            "profile": {
                "discord_id": str(row[0]),
                "username": row[1] or "",
                "display_name": row[2] or row[1] or "Học viên Orbit",
                "avatar_url": row[3] or "",
                "current_streak": active_streak,
                "max_streak": max(max_streak, active_streak),
                "last_study_date": last_date,
                "checked_in_today": checked_in_today,
                "study_xp": study_xp,
                "level": rank_info["level"],
                "rank_title": rank_info["title"],
                "next_xp": rank_info["next_xp"],
                "level_progress": rank_info["progress"],
                "pomodoro_count": row[8] or 0,
                "study_minutes": row[9] or 0,
                "exams_completed": row[10] or 0,
                "docs_contributed": docs_contributed,
                "dream_school": row[12] or "",
                "dream_score": row[13] or "",
                "updated_at": row[14] or "",
            },
        })

    async def handle_study_checkin(self, request: web.Request) -> web.Response:
        """POST /api/study/checkin: Điểm danh chuỗi ngày học (Daily Streak), ghi nhận hoàn thành Pomodoro (25p) hoặc Làm Đề Thi."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            body = {}

        # Xác thực qua Bearer token hoặc thông tin user từ client
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
        verified_user = None
        if token and not self._is_valid_bot_api_secret(token):
            verified_user = await self._verify_discord_bearer_token(token)

        discord_id = 0
        if verified_user:
            try:
                discord_id = int(verified_user.get("id", 0))
            except (ValueError, TypeError):
                discord_id = 0
        if not discord_id and body.get("discord_id"):
            try:
                discord_id = int(body.get("discord_id"))
            except (ValueError, TypeError):
                discord_id = 0

        if not discord_id:
            return web.json_response({"error": "Vui lòng liên kết tài khoản Discord để đồng bộ Chuỗi Ngày Học."}, status=401)

        action = str(body.get("action", "daily_checkin")).strip().lower()
        minutes_added = max(0, min(int(body.get("minutes", 0) or 0), 240))
        username = (verified_user.get("username") if verified_user else None) or str(body.get("username", "")).strip()
        display_name = (
            (verified_user.get("global_name") if verified_user else None)
            or str(body.get("display_name", "")).strip()
            or username
            or f"Học viên #{str(discord_id)[-4:]}"
        )
        avatar_url = str(body.get("avatar_url", "")).strip()
        if verified_user and verified_user.get("avatar") and not avatar_url:
            avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{verified_user['avatar']}.png"

        today_str, yesterday_str = self._get_vn_today_str()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Lấy hồ sơ hiện tại
        row = await self.bot.db.fetchone(
            """
            SELECT current_streak, max_streak, last_study_date, study_xp,
                   pomodoro_count, study_minutes, exams_completed, docs_contributed,
                   dream_school, dream_score, username, display_name, avatar_url
            FROM study_profiles
            WHERE discord_id = ?
            """,
            discord_id,
        )

        contrib_row = await self.bot.db.fetchone(
            "SELECT COUNT(*) FROM documents_archive WHERE author_id = ?",
            discord_id,
        )
        real_contributed = contrib_row[0] if contrib_row else 0

        if row:
            cur_streak = row[0] or 0
            max_streak = row[1] or 0
            last_date = row[2] or ""
            study_xp = row[3] or 0
            pomo_count = row[4] or 0
            study_mins = row[5] or 0
            exams_done = row[6] or 0
            docs_contrib = max(row[7] or 0, real_contributed)
            dream_school = row[8] or ""
            dream_score = row[9] or ""
            username = username or row[10] or ""
            display_name = display_name or row[11] or username
            avatar_url = avatar_url or row[12] or ""
        else:
            cur_streak = 0
            max_streak = 0
            last_date = ""
            study_xp = real_contributed * 50
            pomo_count = 0
            study_mins = 0
            exams_done = 0
            docs_contrib = real_contributed
            dream_school = ""
            dream_score = ""

        xp_gained = 0
        streak_incremented = False

        # Cập nhật chuỗi ngày học nếu hôm nay chưa check-in (trừ khi chỉ đổi mục tiêu trường)
        if action in ("daily_checkin", "pomodoro", "exam_complete"):
            if last_date != today_str:
                if last_date == yesterday_str:
                    cur_streak += 1
                else:
                    cur_streak = 1
                max_streak = max(max_streak, cur_streak)
                last_date = today_str
                xp_gained += 50 + min(cur_streak * 5, 50)
                streak_incremented = True

        if action == "pomodoro":
            pomo_count += 1
            study_mins += (minutes_added if minutes_added > 0 else 25)
            xp_gained += 35
        elif action == "exam_complete":
            exams_done += 1
            study_mins += (minutes_added if minutes_added > 0 else 45)
            xp_gained += 100
        elif action == "update_dream":
            if "dream_school" in body:
                dream_school = str(body.get("dream_school") or "").strip()[:120]
            if "dream_score" in body:
                dream_score = str(body.get("dream_score") or "").strip()[:30]
            if dream_school and study_xp == 0:
                xp_gained += 20

        study_xp += xp_gained

        await self.bot.db.execute(
            """
            INSERT INTO study_profiles
            (discord_id, username, display_name, avatar_url, current_streak, max_streak,
             last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
             docs_contributed, dream_school, dream_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = CASE WHEN excluded.avatar_url != '' THEN excluded.avatar_url ELSE study_profiles.avatar_url END,
                current_streak = excluded.current_streak,
                max_streak = excluded.max_streak,
                last_study_date = excluded.last_study_date,
                study_xp = excluded.study_xp,
                pomodoro_count = excluded.pomodoro_count,
                study_minutes = excluded.study_minutes,
                exams_completed = excluded.exams_completed,
                docs_contributed = excluded.docs_contributed,
                dream_school = excluded.dream_school,
                dream_score = excluded.dream_score,
                updated_at = excluded.updated_at
            """,
            discord_id, username, display_name, avatar_url,
            cur_streak, max_streak, last_date, study_xp,
            pomo_count, study_mins, exams_done, docs_contrib,
            dream_school, dream_score, now_iso,
        )

        # Đồng bộ luôn sang bảng users (ranked_streak / ranked_max_streak) nếu có trong SQLAlchemy
        try:
            await self.bot.db.execute(
                "UPDATE users SET ranked_streak = ?, ranked_max_streak = MAX(COALESCE(ranked_max_streak, 0), ?) WHERE discord_id = ?",
                cur_streak, max_streak, discord_id,
            )
        except Exception:
            pass

        # Đồng bộ lên Turso Cloud nền để Web truy cập được ngay cả khi Bot tắt
        try:
            from database.turso_client import turso_db
            if turso_db.is_configured:
                await turso_db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS study_profiles (
                        discord_id INTEGER PRIMARY KEY,
                        username TEXT,
                        display_name TEXT,
                        avatar_url TEXT,
                        current_streak INTEGER DEFAULT 0,
                        max_streak INTEGER DEFAULT 0,
                        last_study_date TEXT DEFAULT '',
                        study_xp INTEGER DEFAULT 0,
                        pomodoro_count INTEGER DEFAULT 0,
                        study_minutes INTEGER DEFAULT 0,
                        exams_completed INTEGER DEFAULT 0,
                        docs_contributed INTEGER DEFAULT 0,
                        dream_school TEXT DEFAULT '',
                        dream_score TEXT DEFAULT '',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await turso_db.execute(
                    """
                    INSERT INTO study_profiles
                    (discord_id, username, display_name, avatar_url, current_streak, max_streak,
                     last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
                     docs_contributed, dream_school, dream_score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        username = excluded.username,
                        display_name = excluded.display_name,
                        avatar_url = CASE WHEN excluded.avatar_url != '' THEN excluded.avatar_url ELSE study_profiles.avatar_url END,
                        current_streak = excluded.current_streak,
                        max_streak = excluded.max_streak,
                        last_study_date = excluded.last_study_date,
                        study_xp = excluded.study_xp,
                        pomodoro_count = excluded.pomodoro_count,
                        study_minutes = excluded.study_minutes,
                        exams_completed = excluded.exams_completed,
                        docs_contributed = excluded.docs_contributed,
                        dream_school = excluded.dream_school,
                        dream_score = excluded.dream_score,
                        updated_at = excluded.updated_at
                    """,
                    discord_id, username, display_name, avatar_url,
                    cur_streak, max_streak, last_date, study_xp,
                    pomo_count, study_mins, exams_done, docs_contrib,
                    dream_school, dream_score, now_iso,
                )
        except Exception as te:
            logger.debug(f"Turso sync study_profiles skipped: {te}")

        rank_info = self._compute_study_rank(study_xp, cur_streak)
        return web.json_response({
            "success": True,
            "xp_gained": xp_gained,
            "streak_incremented": streak_incremented,
            "profile": {
                "discord_id": str(discord_id),
                "username": username,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "current_streak": cur_streak,
                "max_streak": max_streak,
                "last_study_date": last_date,
                "checked_in_today": (last_date == today_str),
                "study_xp": study_xp,
                "level": rank_info["level"],
                "rank_title": rank_info["title"],
                "next_xp": rank_info["next_xp"],
                "level_progress": rank_info["progress"],
                "pomodoro_count": pomo_count,
                "study_minutes": study_mins,
                "exams_completed": exams_done,
                "docs_contributed": docs_contrib,
                "dream_school": dream_school,
                "dream_score": dream_score,
                "updated_at": now_iso,
            },
        })

    async def handle_study_leaderboard(self, request: web.Request) -> web.Response:
        """GET /api/study/leaderboard: Bảng xếp hạng học thuật đồng bộ giữa Discord Bot và Web Hub."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

        today_str, yesterday_str = self._get_vn_today_str()

        # 1. Tự động đồng bộ những người đóng góp đề thi từ documents_archive & linked_accounts vào study_profiles
        try:
            contrib_rows = await self.bot.db.fetchall(
                """
                SELECT author_id, MAX(author_name), COUNT(*) as cnt
                FROM documents_archive
                WHERE author_id IS NOT NULL AND author_id > 0
                GROUP BY author_id
                """
            )
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for c_row in contrib_rows:
                aid, aname, cnt = c_row[0], c_row[1] or "Thành viên Orbit", c_row[2] or 0
                await self.bot.db.execute(
                    """
                    INSERT INTO study_profiles
                    (discord_id, username, display_name, avatar_url, current_streak, max_streak,
                     last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
                     docs_contributed, dream_school, dream_score, updated_at)
                    VALUES (?, ?, ?, '', 1, 1, ?, ?, 0, 0, 0, ?, '', '', ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        docs_contributed = MAX(study_profiles.docs_contributed, excluded.docs_contributed),
                        study_xp = MAX(study_profiles.study_xp, excluded.docs_contributed * 50)
                    """,
                    aid, aname, aname, today_str, cnt * 50, cnt, now_iso,
                )
        except Exception as se:
            logger.debug(f"Auto-seed study_profiles from documents_archive skipped: {se}")

        rows = await self.bot.db.fetchall(
            """
            SELECT sp.discord_id,
                   COALESCE(NULLIF(sp.display_name, ''), NULLIF(la.global_name, ''), NULLIF(sp.username, ''), 'Học viên Orbit') as dname,
                   COALESCE(NULLIF(sp.username, ''), la.username, '') as uname,
                   COALESCE(NULLIF(sp.avatar_url, ''), la.avatar_url, '') as avatar,
                   sp.current_streak, sp.max_streak, sp.last_study_date,
                   sp.study_xp, sp.pomodoro_count, sp.study_minutes,
                   sp.exams_completed, sp.docs_contributed, sp.dream_school, sp.dream_score
            FROM study_profiles sp
            LEFT JOIN linked_accounts la ON sp.discord_id = la.discord_id
            ORDER BY sp.study_xp DESC, sp.current_streak DESC, sp.exams_completed DESC
            LIMIT 30
            """
        )

        scholars = []
        for idx, r in enumerate(rows):
            last_d = r[6] or ""
            active_streak = (r[4] or 0) if last_d in (today_str, yesterday_str) else 0
            max_s = max(r[5] or 0, active_streak)
            xp = r[7] or 0
            r_info = self._compute_study_rank(xp, active_streak)
            scholars.append({
                "rank": idx + 1,
                "discord_id": str(r[0]),
                "display_name": r[1],
                "username": r[2],
                "avatar_url": r[3],
                "current_streak": active_streak,
                "max_streak": max_s,
                "study_xp": xp,
                "level": r_info["level"],
                "rank_title": r_info["title"],
                "pomodoro_count": r[8] or 0,
                "study_minutes": r[9] or 0,
                "exams_completed": r[10] or 0,
                "docs_contributed": r[11] or 0,
                "dream_school": r[12] or "",
                "dream_score": r[13] or "",
            })

        return web.json_response({
            "success": True,
            "total": len(scholars),
            "leaderboard": scholars,
        })

    async def handle_check_hash(self, request: web.Request) -> web.Response:
        """GET /api/documents/check_hash?hash=...: Kiểm tra nhanh mã SHA-256 chống nộp trùng lặp."""
        file_hash = request.query.get("hash", "").strip()
        if not file_hash or len(file_hash) != 64:
            return web.json_response({"error": "Mã hash không hợp lệ (yêu cầu 64 ký tự SHA-256)"}, status=400)

        existing = None
        if hasattr(self.bot, "db"):
            existing = await self.bot.db.fetchone(
                "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_hash = ?",
                file_hash,
            )

        if not existing:
            try:
                from database.turso_client import turso_db
                if turso_db.is_configured:
                    existing_t = await turso_db.fetchone(
                        "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_hash = ?",
                        file_hash,
                    )
                    if existing_t:
                        existing = (
                            existing_t.get("id"),
                            existing_t.get("title"),
                            existing_t.get("author_name"),
                            existing_t.get("timestamp"),
                            existing_t.get("jump_url"),
                        )
            except Exception:
                pass

        if existing:
            return web.json_response({
                "exists": True,
                "is_duplicate": True,
                "message": f"Tài liệu trùng lặp! Tệp '{existing[1]}' đã được nộp trước đó bởi '{existing[2]}' vào {existing[3]}.",
                "doc_id": existing[0],
                "title": existing[1],
            })

        return web.json_response({"exists": False, "is_duplicate": False})

    async def handle_upload_document(self, request: web.Request) -> web.Response:
        """POST /api/documents/upload: Kéo thả / Nộp đề thi từ Web Dashboard và gọi Bot DocInspector nhận dạng."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        # 1. BẮT BUỘC XÁC THỰC DISCORD VÀ EMAIL ĐÃ XÁC MINH TRÊN SERVER
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "X-Bot-Secret" in request.headers:
            token = request.headers["X-Bot-Secret"].strip()

        user_data = None
        is_bot_admin = False
        if self._is_valid_bot_api_secret(token):
            is_bot_admin = True
            uploader_name = "Bot Administrator"
            uploader_id = 0
        elif token:
            user_data = await self._verify_discord_bearer_token(token)

        if not is_bot_admin:
            if not user_data:
                # Chế độ mở: khách không đăng nhập vẫn được nộp (chống spam bằng rate-limit IP bên dưới)
                uploader_id = 0
                uploader_name = "Khách"
            else:
                # KIỂM TRA EMAIL ĐÃ XÁC MINH (Chặn hoàn toàn bypass phía client)
                if not user_data.get("verified", False):
                    return web.json_response({
                        "error": "Tài khoản Discord chưa xác minh Email",
                        "message": "Tài khoản Discord của bạn chưa xác minh Email (Unverified). Discord Bot chỉ chấp nhận tài liệu từ tài khoản đã xác minh email.",
                    }, status=403)

                # Lấy thông tin tác giả TRỰC TIẾP TỪ DISCORD API - KHÔNG TIN DỮ LIỆU TỪ CLIENT
                uploader_id = int(user_data.get("id", 0))
                uploader_name = user_data.get("global_name") or user_data.get("username") or "Discord User"

        # Rate Limiting: tối đa 100 tệp trong 5 phút trên mỗi IP (cho phép nộp vô hạn theo đợt, chống spam)
        client_ip = request.remote or "unknown"
        now = time.time()
        upload_history = [t for t in self._upload_rate_limits.get(client_ip, []) if now - t < 300.0]
        if len(upload_history) >= 100:
            return web.json_response({
                "error": "Quá nhiều tệp được nộp",
                "message": "Bạn đã vượt quá giới hạn nộp tài liệu (tối đa 100 tệp trong 5 phút). Vui lòng thử lại sau.",
            }, status=429)
        upload_history.append(now)
        self._upload_rate_limits[client_ip] = upload_history

        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"error": "Yêu cầu phải là định dạng multipart/form-data"}, status=400)

        file_bytes = None
        file_name = "de_thi_upload.pdf"
        custom_subject = ""
        custom_grade = ""
        client_pre_parsed = False
        client_hash = ""
        moet_part1_count = 0
        moet_part2_count = 0
        moet_part3_count = 0
        moet_2025_compliant = False
        has_answer_keys = False
        has_detailed_solutions = False
        client_year = ""
        client_school = ""
        client_summary = ""
        client_exam_type = ""
        client_question_count = 0

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                file_name = part.filename or "de_thi_upload.pdf"
                file_bytes = await part.read()
            elif part.name == "subject":
                custom_subject = (await part.text()).strip()
            elif part.name == "grade":
                custom_grade = (await part.text()).strip()
            elif part.name == "client_pre_parsed":
                client_pre_parsed = (await part.text()).strip().lower() in ("true", "1")
            elif part.name == "file_hash":
                client_hash = (await part.text()).strip()
            elif part.name == "moet_2025_compliant":
                moet_2025_compliant = (await part.text()).strip().lower() in ("true", "1")
            elif part.name == "moet_part1_count":
                try:
                    moet_part1_count = int((await part.text()).strip())
                except Exception:
                    pass
            elif part.name == "moet_part2_count":
                try:
                    moet_part2_count = int((await part.text()).strip())
                except Exception:
                    pass
            elif part.name == "moet_part3_count":
                try:
                    moet_part3_count = int((await part.text()).strip())
                except Exception:
                    pass
            elif part.name == "has_answer_keys":
                has_answer_keys = (await part.text()).strip().lower() in ("true", "1")
            elif part.name == "has_detailed_solutions":
                has_detailed_solutions = (await part.text()).strip().lower() in ("true", "1")
            elif part.name == "academic_year":
                client_year = (await part.text()).strip()
            elif part.name == "school_or_department":
                client_school = (await part.text()).strip()
            elif part.name == "summary":
                client_summary = (await part.text()).strip()
            elif part.name == "exam_type":
                client_exam_type = (await part.text()).strip()
            elif part.name == "question_count":
                try:
                    client_question_count = int((await part.text()).strip())
                except Exception:
                    pass

        if not file_bytes:
            return web.json_response({"error": "Không tìm thấy tệp đính kèm để nộp"}, status=400)

        # 2. KIỂM TRA TÊN TỆP & CHỐNG PATH TRAVERSAL (CWE-22)
        import re
        safe_name = os.path.basename(file_name)
        safe_name = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", safe_name).strip()
        safe_name = safe_name.replace("..", "")
        while safe_name.startswith("."):
            safe_name = safe_name[1:].strip()
        file_name = safe_name if (safe_name and any(c.isalnum() for c in safe_name)) else "tai_lieu.pdf"

        # 3. KIỂM TRA DUNG LƯỢNG TỆP TỐI ĐA 25 MB (CWE-434)
        if len(file_bytes) > 25 * 1024 * 1024:
            return web.json_response({
                "error": "Dung lượng tệp quá lớn",
                "message": f"Dung lượng tệp vượt quá giới hạn tối đa 25 MB ({len(file_bytes)/(1024*1024):.1f} MB).",
            }, status=413)

        # 4. CHẶN TỆP THỰC THI & TẬP LỆNH NGUY HIỂM (Chống Remote Code Execution / CWE-434)
        if (
            file_bytes.startswith(b"MZ")  # Windows PE/EXE/DLL
            or file_bytes.startswith(b"\x7fELF")  # Linux ELF executable
            or file_bytes.startswith(b"\xca\xfe\xba\xbe")  # Java bytecode / Mach-O Fat
            or file_bytes.startswith(b"<?php")  # PHP script
            or file_bytes.startswith(b"#!\x2f")  # Shell script / shebang
        ):
            return web.json_response({
                "error": "Tệp nguy hiểm bị từ chối",
                "message": "Hệ thống từ chối tệp chứa mã thực thi nhị phân hoặc tập lệnh hệ thống.",
            }, status=400)

        # 5. KIỂM TRA MAGIC BYTES TRÊN SERVER (Chống File Spoofing / Polyglot files)
        allowed_magic = False
        if file_bytes.startswith(b"%PDF"):
            allowed_magic = True
        elif file_bytes.startswith(b"PK\x03\x04"):  # DOCX, XLSX, ZIP
            allowed_magic = True
        elif file_bytes.startswith(b"\xD0\xCF\x11\xE0"):  # DOC OLE2
            allowed_magic = True
        elif file_name.lower().endswith((".txt", ".md", ".json")):
            # Kiểm tra tệp văn bản không chứa null bytes hoặc mã nhúng HTML/SVG/Script độc hại
            lower_head = file_bytes[:4096].lower()
            if (
                b"\x00" in file_bytes[:1024]
                or b"<script" in lower_head
                or b"<iframe" in lower_head
                or b"<svg" in lower_head
                or b"javascript:" in lower_head
            ):
                return web.json_response({
                    "error": "Nội dung tệp văn bản không an toàn",
                    "message": "Tệp văn bản chứa ký tự điều khiển hoặc thẻ mã độc (HTML/Script Injection).",
                }, status=400)
            allowed_magic = True

        if not allowed_magic:
            return web.json_response({
                "error": "Định dạng tệp không được hỗ trợ",
                "message": "Hệ thống chỉ chấp nhận tệp tài liệu PDF, DOCX, DOC, XLSX hoặc văn bản thuần hợp lệ.",
            }, status=415)

        # 1. Tính hoặc tái sử dụng SHA-256 hash của tệp
        file_hash = None
        if client_hash and len(client_hash) == 64:
            file_hash = client_hash
        else:
            try:
                from cpp_core.bridge import fast_sha256
                file_hash = fast_sha256(file_bytes)
            except Exception:
                import hashlib
                file_hash = hashlib.sha256(file_bytes).hexdigest()

        # 2. Kiểm tra trùng lặp trong kho (bằng mã băm SHA-256 hoặc tên tệp + dung lượng)
        existing = await self.bot.db.fetchone(
            "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_hash = ?",
            file_hash,
        )
        if not existing and file_name:
            existing = await self.bot.db.fetchone(
                "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_name = ? AND file_size_bytes = ?",
                file_name,
                len(file_bytes),
            )

        if existing:
            return web.json_response({
                "success": False,
                "is_duplicate": True,
                "message": f"Tài liệu trùng lặp! Tệp '{file_name}' đã được nộp trước đó bởi '{existing[2]}' vào {existing[3]}.",
                "existing_id": existing[0],
                "existing_title": existing[1],
                "file_hash": file_hash,
            })

        # 3. Phân tích nội dung tệp (ƯU TIÊN CLIENT PRE-PARSED ĐỂ GIẢM 90% CPU VPS)
        detected_subject = custom_subject or "MATHEMATICS"
        detected_grade = custom_grade or "Chung ( chung cho tất cả khối )"
        exam_type_str = "THI_THU_THPT"
        confidence = 0.95
        question_count = 0
        page_count = max(1, len(file_bytes) // (150 * 1024))
        raw_text_summary = ""
        academic_year = None
        school_name = None

        if client_pre_parsed and custom_subject:
            # === CLIENT OFF-LOADING: BỎ QUA HOÀN TOÀN BỘ PHÂN TÍCH PYTHON NẶNG TRÊN VPS ===
            detected_subject = custom_subject
            detected_grade = custom_grade or "Khối 12 (Ôn thi THPT)"
            exam_type_str = client_exam_type or "THI_THU_THPT"
            confidence = 0.98
            question_count = client_question_count or (moet_part1_count + moet_part2_count + moet_part3_count)
            raw_text_summary = client_summary or f"Tài liệu {detected_subject} {detected_grade}"
            academic_year = client_year or None
            school_name = client_school or None
        else:
            try:
                from DocInspector.core import DocumentInspector
                report = await asyncio.to_thread(
                    DocumentInspector.inspect,
                    file_path_or_bytes=file_bytes,
                    file_name=file_name,
                )
                if report:
                    detected_subject = getattr(report.detected_subject, "name", str(report.detected_subject))
                    detected_grade = getattr(report, "grade_level_label_vi", str(report.grade_level))
                    exam_type_str = getattr(report.exam_type, "value", str(report.exam_type))
                    confidence = round(getattr(report, "confidence_score", 0.95), 2)
                    raw_text_summary = getattr(report, "human_summary", "")
                    academic_year = getattr(report, "academic_year", None)
                    school_name = getattr(report, "school_or_department", None)
                    moet_2025_compliant = getattr(report, "moet_2025_compliant", False)
                    moet_part1_count = getattr(report, "moet_part1_count", 0)
                    moet_part2_count = getattr(report, "moet_part2_count", 0)
                    moet_part3_count = getattr(report, "moet_part3_count", 0)
                    has_answer_keys = getattr(report, "has_answer_keys", False)
                    has_detailed_solutions = getattr(report, "has_detailed_solutions", False)
                    if hasattr(report, "pass1") and report.pass1:
                        question_count = getattr(report.pass1, "question_count", 0)
                        page_count = getattr(report.pass1, "page_count", 1)

                    # Layer 2: Kiểm tra trùng nội dung đề thi (Content Hash)
                    content_hash = getattr(report, "content_hash", None)
                    if content_hash and hasattr(self.bot, "db"):
                        existing_content = await self.bot.db.fetchone(
                            "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE content_hash = ? LIMIT 1",
                            content_hash,
                        )
                        if existing_content:
                            return web.json_response({
                                "success": False,
                                "is_duplicate": True,
                                "match_type": "CONTENT_EXACT",
                                "message": f"Nội dung đề thi hoàn toàn trùng khớp với đề '{existing_content[1]}' do '{existing_content[2]}' nộp vào {existing_content[3]}!",
                                "existing_id": existing_content[0],
                                "existing_title": existing_content[1],
                                "file_hash": file_hash,
                                "content_hash": content_hash,
                            })
            except Exception as e:
                logger.warning(f"Lỗi khi chạy DocInspector: {e}")

        # 4. Lưu tệp lên ổ đĩa local để phục vụ tải về / xem trước
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        file_ext = os.path.splitext(file_name)[1].lower().replace(".", "").upper() or "PDF"

        # 4b. Đẩy tệp lên kênh Discord #database (ID: 1548627763467128912) để lấy link CDN phục vụ Web Vercel 24/7
        db_channel_id = int(getattr(settings, "DATABASE_ARCHIVE_CHANNEL_ID", 1548627763467128912) or 1548627763467128912)
        saved_channel_id = 0
        saved_message_id = 0
        saved_jump_url = "https://orbit-psi-black.vercel.app/#vault"
        discord_cdn_url = ""
        try:
            db_chan = self.bot.get_channel(db_channel_id)
            if db_chan is None:
                db_chan = await self.bot.fetch_channel(db_channel_id)
            if db_chan and hasattr(db_chan, "send"):
                import io as _io
                d_file = discord.File(_io.BytesIO(file_bytes), filename=file_name)
                sent_msg = await db_chan.send(
                    content=(
                        f"📦 **[ORBIT DATABASE ARCHIVE]** `{file_name}`\n"
                        f"• **Môn:** `{detected_subject}` • **Khối:** `{detected_grade}` • **Người nộp:** `{uploader_name}`"
                    ),
                    file=d_file,
                )
                saved_channel_id = db_channel_id
                saved_message_id = sent_msg.id
                saved_jump_url = sent_msg.jump_url
                if sent_msg.attachments:
                    discord_cdn_url = sent_msg.attachments[0].url
        except Exception as d_err:
            logger.warning(f"Không thể đẩy tệp lên kênh Discord #database ({db_channel_id}): {d_err}")

        # 5. Lưu vào database documents_archive (Local SQLite)
        try:
            insert_sql = """
                INSERT INTO documents_archive (
                    subject, title, file_name, file_size_bytes, file_type,
                    estimated_level, question_count, page_count, author_id,
                    author_name, channel_id, message_id, jump_url, timestamp,
                    file_hash, raw_text, notes, academic_year, school_or_department,
                    verdict, exam_track, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            await self.bot.db.execute(
                insert_sql,
                detected_subject,
                file_name,
                file_name,
                len(file_bytes),
                file_ext,
                detected_grade,
                question_count,
                page_count,
                uploader_id,
                uploader_name,
                saved_channel_id,
                saved_message_id,
                saved_jump_url,
                now_iso,
                file_hash,
                raw_text_summary[:50000] if raw_text_summary else "",
                raw_text_summary,
                academic_year,
                school_name,
                "XAC_MINH",
                exam_type_str,
                confidence,
            )
        except Exception:
            insert_sql = """
                INSERT INTO documents_archive (
                    subject, title, file_name, file_size_bytes, file_type,
                    estimated_level, question_count, page_count, author_id,
                    author_name, channel_id, message_id, jump_url, timestamp,
                    file_hash, raw_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            await self.bot.db.execute(
                insert_sql,
                detected_subject,
                file_name,
                file_name,
                len(file_bytes),
                file_ext,
                detected_grade,
                question_count,
                page_count,
                uploader_id,
                uploader_name,
                saved_channel_id,
                saved_message_id,
                saved_jump_url,
                now_iso,
                file_hash,
                raw_text_summary[:50000] if raw_text_summary else "",
            )

        # Lấy ID của đề vừa thêm
        row_id_res = await self.bot.db.fetchone("SELECT last_insert_rowid()")
        doc_id = row_id_res[0] if row_id_res else 0

        # Lưu file vật lý
        local_path = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{file_name}"))
        real_upload_dir = os.path.realpath(upload_dir)
        if not local_path.startswith(real_upload_dir + os.sep):
            return web.json_response({"error": "Đường dẫn tệp không an toàn"}, status=400)

        try:
            with open(local_path, "wb") as f:
                f.write(file_bytes)
        except Exception as fe:
            logger.warning(f"Không thể lưu file upload: {fe}")

        # 6. Đồng bộ sang Turso libSQL Cloud Database (Kho 5GB) & Lưu luôn doc_cdn_{doc_id}
        try:
            from database.turso_client import turso_db
            if turso_db.is_configured:
                turso_sql = """
                    INSERT INTO documents_archive (
                        subject, title, file_name, file_size_bytes, file_type,
                        estimated_level, question_count, page_count, author_id,
                        author_name, channel_id, message_id, jump_url, timestamp,
                        file_hash, raw_text, notes, academic_year, school_or_department,
                        verdict, exam_track, confidence, moet_2025_compliant,
                        moet_part1_count, moet_part2_count, moet_part3_count,
                        has_answer_keys, has_detailed_solutions, queue_status,
                        client_pre_parsed, created_via
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?
                    )
                """
                await turso_db.execute(
                    turso_sql,
                    detected_subject, file_name, file_name, len(file_bytes), file_ext,
                    detected_grade, question_count, page_count, uploader_id,
                    uploader_name, saved_channel_id, saved_message_id, saved_jump_url, now_iso,
                    file_hash, raw_text_summary[:50000] if raw_text_summary else "",
                    raw_text_summary, academic_year, school_name,
                    "XAC_MINH", exam_type_str, confidence,
                    1 if moet_2025_compliant else 0,
                    moet_part1_count, moet_part2_count, moet_part3_count,
                    1 if has_answer_keys else 0, 1 if has_detailed_solutions else 0,
                    "synced_discord",
                    1 if client_pre_parsed else 0,
                    "web"
                )
                if discord_cdn_url and doc_id:
                    import json as _json
                    await turso_db.execute(
                        """INSERT INTO bot_kv_store (key, value, updated_at) VALUES (?, ?, ?)
                           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                        f"doc_cdn_{doc_id}",
                        _json.dumps(
                            {"direct_url": discord_cdn_url, "file_name": file_name, "file_type": file_ext},
                            ensure_ascii=False,
                        ),
                        int(time.time()),
                    )
        except Exception as te:
            logger.debug("Không thể đồng bộ đề lên Turso: %s", te)

        self.invalidate_doc_caches()
        return web.json_response({
            "success": True,
            "id": doc_id,
            "title": file_name,
            "file_name": file_name,
            "file_size_bytes": len(file_bytes),
            "file_type": file_ext,
            "detected_subject": detected_subject,
            "estimated_level": detected_grade,
            "exam_type": exam_type_str,
            "confidence_score": confidence,
            "question_count": question_count,
            "page_count": page_count,
            "academic_year": academic_year,
            "school_or_department": school_name,
            "summary": raw_text_summary,
            "file_hash": file_hash,
            "content_hash": getattr(report, "content_hash", None) if "report" in locals() and report else None,
            "quorum": getattr(report, "quorum_arbitration", None) if "report" in locals() and report else None,
            "draft_dossier_markdown": getattr(report, "draft_dossier_markdown", None) if "report" in locals() and report else None,
            "moet_2025_compliant": bool(moet_2025_compliant),
            "moet_part1_count": moet_part1_count,
            "moet_part2_count": moet_part2_count,
            "moet_part3_count": moet_part3_count,
            "has_answer_keys": bool(has_answer_keys),
            "has_detailed_solutions": bool(has_detailed_solutions),
            "download_url": f"/api/documents/{doc_id}/download",
            "message": "Đã tiếp nhận và nhận dạng đề thi thành công! Đề đã được thêm vào Kho Đề.",
        })

    async def handle_import_gdrive(self, request: web.Request) -> web.Response:
        """POST /api/documents/import_gdrive: Tải và nạp tài liệu từ Google Drive link."""
        # 1. Rate Limiting: Tối đa 5 lượt nạp trong 10 phút trên mỗi IP (Chống cạn kiệt tài nguyên)
        client_ip = request.remote or "unknown"
        now = time.time()
        import_history = [t for t in self._import_rate_limits.get(client_ip, []) if now - t < 600.0]
        if len(import_history) >= 5:
            return web.json_response({
                "error": "Quá nhiều yêu cầu nạp từ Google Drive",
                "message": "Bạn đã vượt quá giới hạn nạp Google Drive (tối đa 5 lượt trong 10 phút). Vui lòng thử lại sau.",
            }, status=429)
        import_history.append(now)
        self._import_rate_limits[client_ip] = import_history

        # 2. Yêu cầu Discord Bearer token (đã verify email) hoặc BOT_API_SECRET
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "X-Bot-Secret" in request.headers:
            token = request.headers["X-Bot-Secret"].strip()

        uploader_name = "Web User (Google Drive)"
        if not self._is_valid_bot_api_secret(token):
            user_data = await self._verify_discord_bearer_token(token) if token else None
            if not user_data or not user_data.get("verified", False):
                return web.json_response({
                    "error": "Yêu cầu tài khoản Discord đã xác minh email hoặc quyền quản trị để nạp Google Drive."
                }, status=403)
            uploader_name = user_data.get("global_name") or user_data.get("username") or "Discord User"

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        url = body.get("url", "").strip()

        if not url:
            return web.json_response({"error": "Vui lòng cung cấp đường link Google Drive"}, status=400)

        # 3. CHỐNG SSRF (CWE-918): Xác thực URL Google Drive nghiêm ngặt
        from services.gdrive_importer import is_valid_gdrive_url_or_id
        if not is_valid_gdrive_url_or_id(url):
            return web.json_response({
                "error": "URL Google Drive không hợp lệ hoặc bị chặn vì lý do bảo mật (Chống SSRF).",
                "message": "Chỉ chấp nhận liên kết chính thức từ drive.google.com hoặc docs.google.com.",
            }, status=400)

        try:
            from services.gdrive_importer import download_and_import_gdrive
            results = await asyncio.to_thread(download_and_import_gdrive, url, uploader_name)

            success_items = [r for r in results if r.get("success")]
            duplicate_items = [r for r in results if r.get("is_duplicate")]
            blocked_items = [r for r in results if r.get("blocked")]

            error_msg = ""
            if not success_items:
                if blocked_items:
                    error_msg = blocked_items[0].get("error") or "Tệp bị chặn bởi hệ thống bảo mật 5 lớp."
                elif duplicate_items:
                    error_msg = duplicate_items[0].get("message") or "Tài liệu này đã tồn tại trong kho đề."
                elif results and results[0].get("error"):
                    error_msg = results[0]["error"]

            return web.json_response({
                "success": len(success_items) > 0,
                "total_processed": len(results),
                "new_imported": len(success_items),
                "duplicates": len(duplicate_items),
                "blocked": len(blocked_items),
                "error": error_msg if not success_items else None,
                "results": results,
            })
        except Exception as e:
            logger.error(f"Lỗi khi import Google Drive: {e}", exc_info=True)
            return web.json_response({"error": "Lỗi nội bộ khi xử lý link Google Drive."}, status=500)

    # =========================================================================
    # CÁC ENDPOINT QUẢN TRỊ VIÊN DISCORD & KHO ĐỀ (ADMIN PORTAL)
    # =========================================================================

    async def handle_admin_check(self, request: web.Request) -> web.Response:
        """GET /api/admin/check: Kiểm tra quyền quản trị viên của người dùng hiện tại."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            reason = await self._admin_deny_reason(request)
            hints = {
                "no_token": "Bạn chưa liên kết tài khoản Discord. Hãy đăng nhập bằng Discord trên Web.",
                "unverified": "Tài khoản Discord của bạn chưa xác minh email. Hãy xác minh email rồi thử lại.",
                "not_member": "Bạn chưa tham gia Discord Server Orbit. Hãy vào server rồi thử lại.",
                "not_admin": "Tài khoản của bạn không có role Quản trị (Owner / Co-Owner / Administrator / Moderator).",
            }
            if reason == "no_token":
                logger.debug(f"Admin check skipped (reason=no_token) từ IP {request.remote}")
            else:
                logger.info(f"Admin check DENIED (reason={reason}) từ IP {request.remote}")
            return web.json_response({
                "is_admin": False,
                "reason": reason,
                "message": hints.get(reason, "Tài khoản hiện tại không có quyền Quản trị viên (Admin)."),
            })
        return web.json_response({
            "is_admin": True,
            "admin": admin_info,
        })

    async def handle_admin_bans(self, request: web.Request) -> web.Response:
        """GET /api/admin/bans: Lấy danh sách các tài khoản bị cấm (Bans) trên Discord Server."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        bans = []
        try:
            async for ban_entry in guild.bans(limit=100):
                bans.append({
                    "user_id": str(ban_entry.user.id),
                    "username": ban_entry.user.name,
                    "display_name": getattr(ban_entry.user, "display_name", ban_entry.user.name),
                    "avatar_url": ban_entry.user.display_avatar.url if ban_entry.user.display_avatar else "",
                    "reason": ban_entry.reason or "Không có lý do cụ thể",
                })
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách bans: {e}")
            return web.json_response({"error": f"Lỗi lấy danh sách bans: {e}"}, status=500)

        return web.json_response({"success": True, "total": len(bans), "bans": bans})

    async def handle_admin_channels(self, request: web.Request) -> web.Response:
        """GET /api/admin/channels: Liệt kê kênh text trong server để Admin chọn nơi gửi thông báo."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        channels = []
        try:
            for ch in guild.text_channels:
                channels.append({
                    "channel_id": str(ch.id),
                    "name": f"#{ch.name}",
                    "category": ch.category.name if ch.category else "Không phân loại",
                })
        except Exception as e:
            logger.error(f"Lỗi khi liệt kê kênh Discord: {e}")
            return web.json_response({"error": "Không thể liệt kê kênh Discord"}, status=500)

        channels.sort(key=lambda c: (c["category"], c["name"]))
        return web.json_response({"success": True, "total": len(channels), "channels": channels})

    async def handle_admin_members(self, request: web.Request) -> web.Response:
        """GET /api/admin/members?search=<từ khóa>&limit=25: Tìm thành viên server theo tên để Admin chọn."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        query = (request.query.get("search", "") or "").strip()
        try:
            limit = int(request.query.get("limit", 25))
        except (ValueError, TypeError):
            return web.json_response({"error": "Tham số limit không hợp lệ"}, status=400)
        limit = max(1, min(limit, 50))

        members: list = []
        if query:
            try:
                # Ưu tiên query qua gateway (đầy đủ kể cả member chưa cache)
                members = await guild.query_members(query, limit=limit)
            except Exception as e:
                logger.debug(f"query_members thất bại, fallback cache: {e}")
                members = []

            # Bổ sung lọc substring trong cache (gateway chỉ match prefix)
            try:
                seen_ids = {m.id for m in members}
                q_lower = query.lower()
                for m in guild.members:
                    if len(members) >= limit:
                        break
                    if m.id in seen_ids:
                        continue
                    try:
                        hay = f"{m.name} {m.display_name} {m.nick or ''}".lower()
                        if q_lower in hay:
                            members.append(m)
                            seen_ids.add(m.id)
                    except Exception:
                        continue
            except Exception:
                pass
        else:
            # Không từ khóa: liệt kê N thành viên đầu (sắp xếp: người trước, bot sau)
            try:
                cached = sorted(
                    guild.members,
                    key=lambda m: (bool(getattr(m, "bot", False)), (getattr(m, "display_name", "") or "").lower()),
                )
                members = cached[:limit]
            except Exception:
                members = list(guild.members)[:limit]

        result = []
        for m in members[:limit]:
            try:
                result.append({
                    "user_id": str(m.id),
                    "username": getattr(m, "name", str(m.id)),
                    "display_name": getattr(m, "display_name", getattr(m, "name", str(m.id))),
                    "avatar_url": m.display_avatar.url if getattr(m, "display_avatar", None) else "",
                    "is_bot": getattr(m, "bot", False),
                })
            except Exception:
                continue

        return web.json_response({"success": True, "total": len(result), "members": result})

    @staticmethod
    def _tail_text_file(path: str, max_lines: int = 200, max_bytes: int = 256 * 1024) -> list[str]:
        """Đọc N dòng cuối file hiệu quả (không nạp toàn bộ file log lớn vào RAM)."""
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                pos = size
                chunk = 8192
                buf = b""
                # Đọc ngược cho tới khi đủ dòng hoặc chạm giới hạn bytes
                while pos > 0 and buf.count(b"\n") <= max_lines and len(buf) < max_bytes:
                    step = min(chunk, pos)
                    pos -= step
                    f.seek(pos)
                    buf = f.read(step) + buf
                text = buf.decode("utf-8", errors="replace")
                lines = text.splitlines()
                return lines[-max_lines:]
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"Lỗi đọc log file: {e}")
            return [f"[Không thể đọc log: {e}]"]

    async def handle_admin_logs(self, request: web.Request) -> web.Response:
        """GET /api/admin/logs?lines=200&level=ALL: Đọc N dòng log bot mới nhất cho Admin Console."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        try:
            lines = int(request.query.get("lines", 200))
        except (ValueError, TypeError):
            return web.json_response({"error": "Tham số lines không hợp lệ"}, status=400)
        lines = max(20, min(lines, 1000))
        level = (request.query.get("level", "ALL") or "ALL").upper()
        if level not in ("ALL", "INFO", "WARNING", "ERROR"):
            return web.json_response({"error": "level phải là ALL / INFO / WARNING / ERROR"}, status=400)

        log_path = os.path.join(BOT_BASE_DIR, "logs", "bot.log")
        tail = await asyncio.to_thread(self._tail_text_file, log_path, 1000, 512 * 1024)
        if level != "ALL":
            # Định dạng log: "[INFO    ] ..." nên lọc substring theo mức là đủ chính xác
            tail = [ln for ln in tail if f"[{level}" in ln]
        tail = tail[-lines:]

        try:
            fsize = os.path.getsize(log_path)
        except OSError:
            fsize = 0
        return web.json_response({
            "success": True,
            "level": level,
            "returned_lines": len(tail),
            "log_size_bytes": fsize,
            "lines": tail,
        })

    async def handle_admin_config(self, request: web.Request) -> web.Response:
        """GET /api/admin/config: Cấu hình bot (đã lọc secrets) + trạng thái runtime cho Admin Console."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        import sys
        import discord as _dc

        db_size = 0
        try:
            db_size = os.path.getsize(os.path.join(BOT_BASE_DIR, "data", "bot.db"))
        except OSError:
            pass

        slash_names = []
        try:
            slash_names = sorted(c.name for c in self.bot.tree.get_commands())
        except Exception:
            pass

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        return web.json_response({
            "success": True,
            "bot": {
                "user": str(self.bot.user) if self.bot.user else "?",
                "bot_id": self.bot.user.id if self.bot.user else 0,
                "ping_ms": round(self.bot.latency * 1000, 1) if self.bot.latency else 0.0,
                "uptime_seconds": int(time.time() - START_TIME),
                "guilds_count": len(self.bot.guilds),
                "guild_name": guild.name if guild else "?",
                "guild_id": str(guild.id) if guild else "0",
                "member_count": getattr(guild, "member_count", 0) if guild else 0,
            },
            "runtime": {
                "python": sys.version.split()[0],
                "discord_py": _dc.__version__,
                "cogs_loaded": len(self.bot.extensions),
                "cog_names": sorted(self.bot.extensions.keys()),
                "slash_commands": slash_names,
                "db_size_bytes": db_size,
            },
            "config": {
                # Chỉ các giá trị KHÔNG nhạy cảm (không bao giờ trả token/secret/api key)
                "OWNER_ID": settings.OWNER_ID,
                "BOT_API_HOST": settings.BOT_API_HOST,
                "BOT_API_PORT": settings.BOT_API_PORT,
                "CF_SYNC_INTERVAL_SECONDS": settings.CF_SYNC_INTERVAL_SECONDS,
                "SUBMIT_COOLDOWN_SECONDS": settings.SUBMIT_COOLDOWN_SECONDS,
                "MAX_CODE_LENGTH": settings.MAX_CODE_LENGTH,
                "ANTI_RAID_ENABLED": settings.ANTI_RAID_ENABLED,
                "ANTI_SPAM_ENABLED": settings.ANTI_SPAM_ENABLED,
                "JOIN_FLOOD_THRESHOLD": settings.JOIN_FLOOD_THRESHOLD,
                "MESSAGE_FLOOD_THRESHOLD": settings.MESSAGE_FLOOD_THRESHOLD,
                "BACKUP_AUTO_INTERVAL_HOURS": settings.BACKUP_AUTO_INTERVAL_HOURS,
                "LOG_LEVEL": settings.LOG_LEVEL,
                "DOC_INTAKE_CHANNEL_ID": str(settings.DOC_INTAKE_CHANNEL_ID),
                "DOC_SEARCH_CHANNEL_ID": str(settings.DOC_SEARCH_CHANNEL_ID),
                "LINK_SCANNER_CHANNEL_ID": getattr(settings, "LINK_SCANNER_CHANNEL_ID", 0) and str(settings.LINK_SCANNER_CHANNEL_ID),
            },
        })

    async def handle_admin_audit_logs(self, request: web.Request) -> web.Response:
        """GET /api/admin/audit-logs?limit=50: Nhật ký kiểm toán Discord Server (ban/kick/role/kênh...)."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        try:
            limit = int(request.query.get("limit", 50))
        except (ValueError, TypeError):
            return web.json_response({"error": "Tham số limit không hợp lệ"}, status=400)
        limit = max(1, min(limit, 100))

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        entries = []
        try:
            async for entry in guild.audit_logs(limit=limit):
                try:
                    target = "?"
                    if entry.target:
                        target = getattr(entry.target, "name", None) or getattr(entry.target, "id", "?")
                        target = f"{target} ({entry.target.id})"
                    actor = "?"
                    if entry.user:
                        actor = f"{entry.user.name} ({entry.user.id})"
                    entries.append({
                        "id": str(entry.id),
                        "action": str(entry.action).replace("AuditLogAction.", ""),
                        "actor": actor,
                        "target": str(target),
                        "reason": entry.reason or "",
                        "created_at": entry.created_at.isoformat() if entry.created_at else "",
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Lỗi đọc audit log: {e}")
            return web.json_response({"error": "Không thể đọc nhật ký server (bot thiếu quyền Xem Nhật Ký?)"}, status=500)

        return web.json_response({"success": True, "total": len(entries), "entries": entries})

    async def handle_admin_ban(self, request: web.Request) -> web.Response:
        """POST /api/admin/ban: Cấm người dùng khỏi Discord Server."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        raw_id = body.get("user_id")
        if not raw_id:
            return web.json_response({"error": "Vui lòng cung cấp user_id cần cấm"}, status=400)

        try:
            target_id = int(raw_id)
        except ValueError:
            return web.json_response({"error": "user_id không hợp lệ"}, status=400)

        reason = body.get("reason") or f"Bị cấm từ Web Portal bởi {admin_info.get('username')}"
        reason = str(reason)[:512]
        try:
            delete_message_days = min(max(int(body.get("delete_message_days", 0)), 0), 7)
        except (ValueError, TypeError):
            return web.json_response({"error": "delete_message_days phải là số nguyên 0-7"}, status=400)

        try:
            user_obj = discord.Object(id=target_id)
            await guild.ban(user_obj, reason=reason, delete_message_days=delete_message_days)
            logger.info(f"Admin {admin_info.get('username')} đã BAN user {target_id}. Lý do: {reason}")
            return web.json_response({"success": True, "message": f"Đã cấm tài khoản ID {target_id} thành công!"})
        except Exception as e:
            logger.error(f"Lỗi khi ban user {target_id}: {e}")
            return web.json_response({"error": f"Không thể cấm tài khoản: {e}"}, status=500)

    async def handle_admin_unban(self, request: web.Request) -> web.Response:
        """POST /api/admin/unban: Gỡ cấm người dùng trên Discord Server."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        raw_id = body.get("user_id")
        if not raw_id:
            return web.json_response({"error": "Vui lòng cung cấp user_id cần gỡ cấm"}, status=400)

        try:
            target_id = int(raw_id)
        except ValueError:
            return web.json_response({"error": "user_id không hợp lệ"}, status=400)

        reason = body.get("reason") or f"Gỡ cấm từ Web Portal bởi {admin_info.get('username')}"

        try:
            user_obj = discord.Object(id=target_id)
            await guild.unban(user_obj, reason=reason)
            logger.info(f"Admin {admin_info.get('username')} đã UNBAN user {target_id}")
            return web.json_response({"success": True, "message": f"Đã gỡ cấm tài khoản ID {target_id} thành công!"})
        except Exception as e:
            logger.error(f"Lỗi khi unban user {target_id}: {e}")
            return web.json_response({"error": f"Không thể gỡ cấm: {e}"}, status=500)

    async def handle_admin_kick(self, request: web.Request) -> web.Response:
        """POST /api/admin/kick: Kick thành viên khỏi Discord Server."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        raw_id = body.get("user_id")
        if not raw_id:
            return web.json_response({"error": "Vui lòng cung cấp user_id cần kick"}, status=400)

        try:
            target_id = int(raw_id)
        except ValueError:
            return web.json_response({"error": "user_id không hợp lệ"}, status=400)

        reason = body.get("reason") or f"Bị kick từ Web Portal bởi {admin_info.get('username')}"

        member = guild.get_member(target_id)
        if not member:
            try:
                member = await guild.fetch_member(target_id)
            except Exception:
                member = None

        if not member:
            return web.json_response({"error": "Thành viên không còn ở trong máy chủ Discord"}, status=404)

        try:
            await member.kick(reason=reason)
            logger.info(f"Admin {admin_info.get('username')} đã KICK member {target_id} ({member.name})")
            return web.json_response({"success": True, "message": f"Đã kick thành viên {member.name} thành công!"})
        except Exception as e:
            logger.error(f"Lỗi khi kick member {target_id}: {e}")
            return web.json_response({"error": f"Không thể kick thành viên: {e}"}, status=500)

    async def handle_admin_timeout(self, request: web.Request) -> web.Response:
        """POST /api/admin/timeout: Mute (Timeout) hoặc Unmute thành viên trên Discord."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        raw_id = body.get("user_id")
        if not raw_id:
            return web.json_response({"error": "Vui lòng cung cấp user_id"}, status=400)

        try:
            target_id = int(raw_id)
        except ValueError:
            return web.json_response({"error": "user_id không hợp lệ"}, status=400)

        action = body.get("action", "mute").lower()
        try:
            duration_seconds = int(body.get("duration_seconds", 600))
        except (ValueError, TypeError):
            return web.json_response({"error": "duration_seconds phải là số nguyên (giây)"}, status=400)
        reason = body.get("reason") or f"Xử lý bởi Quản trị viên {admin_info.get('username')}"
        reason = str(reason)[:512]

        member = guild.get_member(target_id)
        if not member:
            try:
                member = await guild.fetch_member(target_id)
            except Exception:
                member = None

        if not member:
            return web.json_response({"error": "Thành viên không còn ở trong máy chủ Discord"}, status=404)

        try:
            if action == "unmute" or duration_seconds <= 0:
                await member.timeout(None, reason=f"Unmute từ Web Portal bởi {admin_info.get('username')}")
                return web.json_response({"success": True, "message": f"Đã gỡ mute (unmute) cho {member.name}!"})
            else:
                duration_seconds = min(duration_seconds, 28 * 86400)
                until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                await member.timeout(until, reason=reason)
                mins = round(duration_seconds / 60, 1)
                return web.json_response({
                    "success": True,
                    "message": f"Đã mute {member.name} trong {mins} phút. Hết hạn lúc: {until.strftime('%H:%M:%S %d/%m/%Y')}!",
                })
        except Exception as e:
            logger.error(f"Lỗi khi timeout member {target_id}: {e}")
            return web.json_response({"error": f"Không thể xử lý mute/unmute: {e}"}, status=500)

    async def handle_admin_archive_document(self, request: web.Request) -> web.Response:
        """POST /api/admin/documents/{id}/archive: Chẻ file thành phần <=25MB, đăng kênh archive, xóa local."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        doc_id_str = request.match_info.get("id", "")
        try:
            doc_id = int(doc_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        try:
            from services.chunk_archive import archive_document
            result = await archive_document(self.bot, self.bot.db, doc_id, delete_local=True)
        except Exception as e:
            logger.error(f"Lỗi archive đề #{doc_id}: {e}", exc_info=True)
            return web.json_response({"error": "Lỗi nội bộ khi offload file"}, status=500)

        if not result.get("success"):
            return web.json_response({"error": result.get("error", "Offload thất bại")}, status=400)
        logger.info(f"Admin {admin_info.get('username')} đã offload đề #{doc_id} ({result.get('parts')} phần).")
        return web.json_response({
            "success": True,
            "message": result.get("message") or f"Đã offload đề #{doc_id} thành {result.get('parts')} phần lên Discord, local đã xóa.",
            "parts": result.get("parts"),
            "total_bytes": result.get("total_bytes"),
        })

    async def handle_admin_archive_lockdown(self, request: web.Request) -> web.Response:
        """POST /api/admin/archive/lockdown: Khóa kênh file-chunks ngay (chỉ admin thấy)."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        try:
            from services.chunk_archive import get_or_create_archive_channel, lock_archive_channel
            channel = await get_or_create_archive_channel(self.bot)
            if not channel:
                return web.json_response({"error": "Không tìm thấy kênh archive"}, status=404)
            result = await lock_archive_channel(self.bot, channel)
        except Exception as e:
            logger.error(f"Lỗi lockdown archive: {e}", exc_info=True)
            return web.json_response({"error": "Lỗi nội bộ khi khóa kênh"}, status=500)

        if not result.get("success"):
            return web.json_response({"error": result.get("error", "Khóa kênh thất bại")}, status=400)
        return web.json_response({
            "success": True,
            "message": f"Đã khóa kênh #{getattr(channel, 'name', '?')}: chỉ bot + admin thấy.",
            "channel_id": result.get("channel_id"),
            "opened_roles": result.get("opened_roles", []),
        })

    async def handle_admin_create_channel(self, request: web.Request) -> web.Response:
        """POST /api/admin/channels {name, kind: voice|text, category_id?, user_limit?, topic?}: Tạo kênh mới."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response({"error": "Máy chủ Discord không khả dụng"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        name = str(body.get("name", "")).strip()
        if not name or len(name) > 100:
            return web.json_response({"error": "Tên kênh không hợp lệ (1-100 ký tự)"}, status=400)
        kind = str(body.get("kind", "voice")).lower()
        if kind not in ("voice", "text"):
            return web.json_response({"error": "kind phải là voice hoặc text"}, status=400)

        category = None
        category_id = body.get("category_id")
        if category_id:
            try:
                category = guild.get_channel(int(category_id))
                if not isinstance(category, discord.CategoryChannel):
                    category = None
            except (ValueError, TypeError):
                return web.json_response({"error": "category_id không hợp lệ"}, status=400)
        if category is None and kind == "voice":
            # Tự tìm mục voice hiện có (chứa kênh voice)
            for cat in guild.categories:
                try:
                    if any(isinstance(c, discord.VoiceChannel) for c in cat.channels):
                        category = cat
                        break
                except Exception:
                    continue

        try:
            user_limit = int(body.get("user_limit", 0) or 0)
        except (ValueError, TypeError):
            return web.json_response({"error": "user_limit phải là số"}, status=400)
        user_limit = max(0, min(user_limit, 99))
        topic = str(body.get("topic", ""))[:200] or None

        try:
            if kind == "voice":
                created = await guild.create_voice_channel(
                    name=name, category=category, user_limit=user_limit or None,
                    reason=f"Tạo bởi {admin_info.get('username')} qua Admin Hub",
                )
            else:
                created = await guild.create_text_channel(
                    name=name, category=category, topic=topic,
                    reason=f"Tạo bởi {admin_info.get('username')} qua Admin Hub",
                )
        except Exception as e:
            logger.error(f"Lỗi tạo kênh {name}: {e}")
            return web.json_response({"error": f"Không thể tạo kênh: {e}"}, status=500)

        logger.info(f"Admin {admin_info.get('username')} đã tạo kênh {kind} #{created.name} ({created.id})")
        return web.json_response({
            "success": True,
            "message": f"Đã tạo kênh #{created.name} thành công!",
            "channel_id": str(created.id),
            "name": created.name,
            "category": category.name if category else "",
        })

    async def handle_admin_channel_lockdown(self, request: web.Request) -> web.Response:
        """POST /api/admin/channels/{id}/lockdown: Ẩn kênh với @everyone, chỉ bot + 4 role admin thấy."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        channel_id_str = request.match_info.get("id", "")
        try:
            channel_id = int(channel_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "ID kênh không hợp lệ"}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel and hasattr(self.bot, "fetch_channel"):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Không tìm thấy kênh text"}, status=404)

        try:
            from services.chunk_archive import lock_archive_channel
            result = await lock_archive_channel(self.bot, channel)
        except Exception as e:
            logger.error(f"Lỗi lockdown kênh {channel_id}: {e}", exc_info=True)
            return web.json_response({"error": "Lỗi nội bộ khi khóa kênh"}, status=500)

        if not result.get("success"):
            return web.json_response({"error": result.get("error", "Khóa kênh thất bại")}, status=400)
        logger.info(f"Admin {admin_info.get('username')} đã khóa kênh #{getattr(channel, 'name', channel_id)}.")
        return web.json_response({
            "success": True,
            "message": f"Đã khóa kênh #{getattr(channel, 'name', channel_id)}: chỉ bot + admin thấy.",
            "channel_id": str(channel.id),
            "opened_roles": result.get("opened_roles", []),
        })

    async def handle_admin_delete_document(self, request: web.Request) -> web.Response:
        """DELETE /api/admin/documents/{id}: Xóa đề thi khỏi CSDL, tệp ổ cứng và tin nhắn Discord."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        doc_id_str = request.match_info.get("id", "")
        try:
            doc_id = int(doc_id_str)
        except ValueError:
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        # Lấy thông tin tài liệu hiện tại
        row = await self.bot.db.fetchone(
            "SELECT id, title, file_name, file_hash, channel_id, message_id FROM documents_archive WHERE id = ?",
            doc_id,
        )
        if not row:
            return web.json_response({"error": f"Không tìm thấy đề thi mang ID #{doc_id}"}, status=404)

        doc_title = row[1]
        file_name = row[2]
        file_hash = row[3]
        channel_id = row[4]
        message_id = row[5]

        # 1. Thử xóa tin nhắn bài đăng trên Discord nếu có
        if channel_id and message_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(message_id)
                    if msg:
                        await msg.delete()
                        logger.info(f"Đã xóa tin nhắn Discord #{message_id} của tài liệu #{doc_id}")
            except Exception as e:
                logger.debug(f"Không thể xóa tin nhắn Discord (có thể đã bị xóa trước đó): {e}")

        # 2. Xóa tệp vật lý trên ổ cứng nếu không có tài liệu khác cùng dùng chung hash
        try:
            same_hash_count = 0
            if file_hash:
                count_row = await self.bot.db.fetchone(
                    "SELECT COUNT(*) FROM documents_archive WHERE file_hash = ? AND id != ?",
                    file_hash, doc_id
                )
                same_hash_count = count_row[0] if count_row else 0

            if same_hash_count == 0 and file_name:
                upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
                if os.path.exists(upload_dir):
                    for candidate in os.listdir(upload_dir):
                        if candidate.lower() == file_name.lower():
                            c_path = os.path.join(upload_dir, candidate)
                            if os.path.isfile(c_path):
                                os.remove(c_path)
                                logger.info(f"Đã xóa tệp vật lý: {c_path}")
                                break
        except Exception as fe:
            logger.debug(f"Lỗi khi xóa tệp vật lý: {fe}")

        # 2b. Xóa các chunk messages trên Discord (nếu đề đã offload) + bản ghi chunks
        try:
            chunk_rows = await self.bot.db.fetchall(
                "SELECT channel_id, message_id FROM document_chunks WHERE doc_id = ? ORDER BY part_no",
                doc_id,
            )
        except Exception:
            chunk_rows = []
        for _ch_id, _msg_id in chunk_rows:
            try:
                _ch = self.bot.get_channel(int(_ch_id))
                if _ch:
                    _msg = await _ch.fetch_message(int(_msg_id))
                    if _msg:
                        await _msg.delete()
            except Exception as e:
                logger.debug(f"Không thể xóa chunk msg {_msg_id}: {e}")
        try:
            await self.bot.db.execute("DELETE FROM document_chunks WHERE doc_id = ?", doc_id)
        except Exception:
            pass

        # 3. Xóa bản ghi trong CSDL (Trigger documents_fts sẽ tự xóa khỏi bảng tìm kiếm FTS5)
        await self.bot.db.execute("DELETE FROM documents_archive WHERE id = ?", doc_id)
        try:
            from database.turso_client import turso_db
            if turso_db.is_configured:
                await turso_db.execute("DELETE FROM documents_archive WHERE id = ?", doc_id)
        except Exception as te:
            logger.debug(f"Không thể đồng bộ xóa đề #{doc_id} trên Turso Cloud: {te}")
        self.invalidate_doc_caches()
        logger.info(f"Admin {admin_info.get('username')} đã xóa hoàn toàn đề thi #{doc_id} ('{doc_title}')")

        return web.json_response({
            "success": True,
            "message": f"Đã xóa thành công đề thi #{doc_id}: '{doc_title}'!",
            "deleted_id": doc_id,
        })

    async def handle_admin_edit_document(self, request: web.Request) -> web.Response:
        """PATCH /api/admin/documents/{id}: Chỉnh sửa tiêu đề, ghi chú (notes), môn học, khối lớp của đề thi."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu bot chưa sẵn sàng"}, status=503)

        doc_id_str = request.match_info.get("id", "")
        try:
            doc_id = int(doc_id_str)
        except ValueError:
            return web.json_response({"error": "ID đề thi không hợp lệ"}, status=400)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Dữ liệu JSON không hợp lệ"}, status=400)

        existing = await self.bot.db.fetchone(
            "SELECT id, title, subject, estimated_level, notes FROM documents_archive WHERE id = ?",
            doc_id,
        )
        if not existing:
            return web.json_response({"error": f"Không tìm thấy đề thi mang ID #{doc_id}"}, status=404)

        cur_title, cur_subject, cur_level, cur_notes = (
            existing[1],
            existing[2],
            existing[3],
            (existing[4] if len(existing) > 4 and existing[4] else ""),
        )

        def _safe_str(value: object, fallback: str, limit: int = 500) -> str:
            try:
                text = str(value if value is not None else fallback)
            except Exception:
                text = fallback
            return text.strip()[:limit] or fallback

        new_title = _safe_str(body.get("title", cur_title), cur_title, 300)
        new_notes = _safe_str(body.get("notes", cur_notes), cur_notes or "", 2000)
        new_subject = _safe_str(body.get("subject", cur_subject), cur_subject, 64)
        new_level = _safe_str(body.get("estimated_level", cur_level), cur_level, 64)

        # Đảm bảo cột notes tồn tại trong DB
        try:
            await self.bot.db.execute("ALTER TABLE documents_archive ADD COLUMN notes TEXT")
        except Exception:
            pass

        await self.bot.db.execute(
            """UPDATE documents_archive
               SET title = ?, subject = ?, estimated_level = ?, notes = ?
               WHERE id = ?""",
            new_title, new_subject, new_level, new_notes, doc_id
        )
        try:
            from database.turso_client import turso_db
            if turso_db.is_configured:
                await turso_db.execute(
                    """UPDATE documents_archive
                       SET title = ?, subject = ?, estimated_level = ?, notes = ?
                       WHERE id = ?""",
                    new_title, new_subject, new_level, new_notes, doc_id
                )
        except Exception as te:
            logger.debug(f"Không thể đồng bộ cập nhật đề #{doc_id} trên Turso Cloud: {te}")
        self.invalidate_doc_caches()
        logger.info(f"Admin {admin_info.get('username')} đã cập nhật đề thi #{doc_id}: '{new_title}', notes='{new_notes}'")

        return web.json_response({
            "success": True,
            "message": f"Đã cập nhật thông tin và ghi chú cho đề thi #{doc_id} thành công!",
            "document": {
                "id": doc_id,
                "title": new_title,
                "subject": new_subject,
                "estimated_level": new_level,
                "notes": new_notes,
            }
        })

    # =========================================================================
    # ENDPOINTS ĐỒNG BỘ HỆ THỐNG, GITHUB UPDATE & HOT-RELOAD
    # =========================================================================

    async def handle_system_update_status(self, request: web.Request) -> web.Response:
        """GET /api/system/update_status: Trả về trạng thái cập nhật GitHub và git commit hiện tại."""
        try:
            from services.system_sync_service import system_sync_service
            git_info = await system_sync_service.get_current_git_info()
            pending = system_sync_service.pending_update
            return web.json_response({
                "current_hash": git_info.get("hash", "dev"),
                "full_hash": git_info.get("full_hash", "dev"),
                "commit_msg": git_info.get("commit_msg", ""),
                "branch": git_info.get("branch", "main"),
                "has_update": bool(pending and pending.get("has_update")),
                "remote_hash": pending.get("remote_hash") if pending else git_info.get("hash", "dev"),
                "commits": pending.get("commits", []) if pending else [],
                "last_check_timestamp": int(system_sync_service._last_check_time),
            })
        except Exception as e:
            logger.error("Lỗi khi lấy update status: %s", e)
            return web.json_response({
                "current_hash": "dev",
                "has_update": False,
                "remote_hash": "dev",
                "commits": [],
                "error": str(e),
            })

    async def handle_system_check_update(self, request: web.Request) -> web.Response:
        """POST /api/system/check_update: Kích hoạt kiểm tra cập nhật GitHub ngay lập tức."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        try:
            from services.system_sync_service import system_sync_service
            result = await system_sync_service.check_github_update()
            if result.get("has_update"):
                # Gửi thông báo đến kênh Discord nếu có update mới
                await system_sync_service.notify_github_update(self.bot, result)
            return web.json_response(result)
        except Exception as e:
            logger.error("Lỗi khi kiểm tra update GitHub: %s", e)
            return web.json_response({"error": f"Lỗi kiểm tra cập nhật: {e}"}, status=500)

    async def handle_system_apply_update(self, request: web.Request) -> web.Response:
        """POST /api/system/apply_update: 1-Click Update từ GitHub và hot-reload toàn bộ bot."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        logger.info(f"Admin {admin_info.get('username')} đã kích hoạt 1-Click Update từ Web Admin Hub!")
        try:
            from services.system_sync_service import system_sync_service
            result = await system_sync_service.perform_system_update(self.bot)
            status_code = 200 if result.get("success") else 500
            return web.json_response(result, status=status_code)
        except Exception as e:
            logger.error("Lỗi khi thực hiện system update: %s", e)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_system_reload(self, request: web.Request) -> web.Response:
        """POST /api/system/reload: Kích hoạt tối ưu & hot-reload hệ thống từ Web Admin Hub."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        logger.info(f"Admin {admin_info.get('username')} đã kích hoạt Hot-Reload từ Web Admin Hub!")
        try:
            from services.system_sync_service import system_sync_service
            summary = await system_sync_service.perform_optimized_reload(self.bot)
            return web.json_response({
                "success": summary.get("success", True),
                "message": f"Đã reload thành công {len(summary.get('reloaded_cogs', []))}/{summary.get('total_cogs', 0)} cogs trong {summary.get('duration_ms')}ms.",
                "reload_summary": summary,
            })
        except Exception as e:
            logger.error("Lỗi khi reload hệ thống: %s", e)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_system_announce_startup(self, request: web.Request) -> web.Response:
        """POST /api/system/announce_startup: Gửi lại thông báo khởi động và link Vercel vào kênh Discord."""
        admin_info = await self._verify_admin_access(request)
        if not admin_info:
            return web.json_response({"error": "Forbidden", "message": "Yêu cầu quyền Quản trị viên"}, status=403)

        try:
            from services.system_sync_service import system_sync_service
            sent = await system_sync_service.send_startup_announcement(self.bot)
            return web.json_response({
                "success": sent,
                "message": "Đã gửi thông báo khởi động và link Vercel vào kênh Discord thành công!" if sent else "Không thể gửi tin nhắn vào Discord.",
            })
        except Exception as e:
            logger.error("Lỗi khi gửi thông báo khởi động: %s", e)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def start(self) -> None:
        """Khởi chạy HTTP Server trên background task."""
        if not settings.BOT_API_ENABLED:
            logger.info("Bot API Bridge bị tắt bởi cấu hình.")
            return

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, settings.BOT_API_HOST, settings.BOT_API_PORT)
        try:
            await self.site.start()
        except OSError as e:
            # Port bị chiếm (thường do 2 bot chạy chồng): báo rõ, không để traceback treo task
            logger.critical(
                f"Không thể mở port {settings.BOT_API_PORT} cho API Bridge ({e}). "
                "Khả năng cao đã có 1 bot khác đang chạy — hãy tắt bot cũ rồi khởi động lại. "
                "Bot Discord vẫn chạy nhưng Web sẽ báo offline."
            )
            try:
                await self.runner.cleanup()
            except Exception:
                pass
            self.runner = None
            self.site = None
            return
        logger.info(
            f"🚀 Bot API Bridge đang hoạt động tại http://{settings.BOT_API_HOST}:{settings.BOT_API_PORT}"
        )
        # Khởi chạy cầu nối 2 chiều trực tiếp với Vercel qua Turso Cloud (Zero-ngrok / Zero-Cloudflare)
        self._turso_relay_task = asyncio.create_task(self._turso_relay_loop())

    async def _init_turso_bridge_tables(self) -> None:
        """Khởi tạo bảng lưu trạng thái thực thi (bot_kv_store) và hàng đợi RPC 2 chiều (bot_rpc_queue) trên Turso Cloud."""
        from database.turso_client import turso_db
        if not turso_db.is_configured:
            return
        await turso_db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        await turso_db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_rpc_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                headers TEXT,
                body TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                response_status INTEGER DEFAULT 200,
                response_body TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        await turso_db.execute(
            """
            CREATE TABLE IF NOT EXISTS linked_accounts (
                discord_id INTEGER PRIMARY KEY,
                username TEXT,
                global_name TEXT,
                avatar_url TEXT,
                email TEXT,
                verified INTEGER DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                login_count INTEGER DEFAULT 1
            )
            """
        )

    async def _push_turso_telemetry_snapshot(self) -> None:
        """Đồng bộ trạng thái Bot Online, Ping, danh sách Admin/Member và dữ liệu Admin Console lên Turso Cloud cho Vercel."""
        import json as _json
        import aiohttp as _aiohttp
        from database.turso_client import turso_db
        if not turso_db.is_configured:
            return

        now_ts = int(time.time())
        uptime = int(now_ts - START_TIME)
        ping = round(self.bot.latency * 1000, 2) if hasattr(self.bot, "latency") and self.bot.latency == self.bot.latency else 0.0

        status_payload = {
            "status": "online",
            "bot_user": str(self.bot.user) if self.bot.user else "Orbit Bot",
            "bot_id": self.bot.user.id if self.bot.user else 0,
            "ping_ms": ping,
            "guilds_count": len(self.bot.guilds) if hasattr(self.bot, "guilds") else 1,
            "uptime_seconds": uptime,
            "timestamp": now_ts,
            "bridge_mode": "vercel_turso_direct",
        }
        await turso_db.execute(
            """INSERT INTO bot_kv_store (key, value, updated_at) VALUES ('status', ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            _json.dumps(status_payload, ensure_ascii=False),
            now_ts,
        )

        # Đồng bộ danh sách Admin & Member IDs để Vercel xác thực /api/admin/check và /api/documents/request_exam tức thì
        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if getattr(self.bot, "guilds", None) else None)
        if guild:
            admins_map: dict[str, dict[str, Any]] = {}
            member_ids: list[str] = []
            for m in guild.members:
                uid_str = str(m.id)
                member_ids.append(uid_str)
                role_ids = {r.id for r in getattr(m, "roles", [])}
                is_owner = (m.id == BOT_OWNER_ID) or (settings.OWNER_ID and m.id == settings.OWNER_ID) or (guild.owner_id == m.id)
                is_adm = is_owner or getattr(m.guild_permissions, "administrator", False) or bool(role_ids.intersection(ADMIN_ROLE_IDS))
                if is_adm:
                    admins_map[uid_str] = {
                        "is_admin": True,
                        "user_id": m.id,
                        "username": m.name,
                        "display_name": m.display_name,
                        "role_name": "👑 Owner" if is_owner else (m.top_role.name if getattr(m, "top_role", None) else "⚡ Administrator"),
                    }
            access_payload = {
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "member_count": guild.member_count or len(member_ids),
                "admins": admins_map,
                "member_ids": member_ids[:5000],
                "updated_at": now_ts,
            }
            await turso_db.execute(
                """INSERT INTO bot_kv_store (key, value, updated_at) VALUES ('guild_access', ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                _json.dumps(access_payload, ensure_ascii=False),
                now_ts,
            )

        # Đồng bộ snapshot các endpoint Admin Console từ local HTTP server lên Turso Cloud
        secret = (getattr(settings, "BOT_API_SECRET", "") or "").strip()
        if not secret:
            return
        local_base = f"http://127.0.0.1:{settings.BOT_API_PORT}"
        headers = {"X-Bot-Secret": secret}
        snapshot_routes = [
            ("admin_channels", "/api/admin/channels"),
            ("admin_members", "/api/admin/members?limit=50"),
            ("admin_bans", "/api/admin/bans"),
            ("admin_logs", "/api/admin/logs?lines=200&level=ALL"),
            ("admin_config", "/api/admin/config"),
            ("admin_audit_logs", "/api/admin/audit-logs"),
            ("system_update_status", "/api/system/update_status"),
        ]
        async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=5.0)) as sess:
            for kv_key, route in snapshot_routes:
                try:
                    async with sess.get(f"{local_base}{route}", headers=headers) as resp:
                        if resp.status == 200:
                            text_val = await resp.text()
                            await turso_db.execute(
                                """INSERT INTO bot_kv_store (key, value, updated_at) VALUES (?, ?, ?)
                                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                                kv_key,
                                text_val,
                                now_ts,
                            )
                except Exception:
                    pass

            # Làm nóng sẵn (Pre-warm) tối đa 2 đề thi/chu kỳ lên Turso Cloud để Vercel đọc PDF & làm đề 24/7 khi tắt PC
            try:
                await self._prewarm_turso_documents_cache(sess, local_base)
            except Exception as pw_err:
                logger.debug(f"Pre-warm Turso documents cache skip: {pw_err}")

    async def _prewarm_turso_documents_cache(self, sess: Any, local_base: str) -> None:
        """Tự động đồng bộ ngầm link Discord CDN (doc_cdn_{id}) và raw_text của kho đề lên Turso Cloud theo từng lô nhỏ."""
        from database.turso_client import turso_db
        if not turso_db.is_configured or not hasattr(self.bot, "db") or not self.bot.db:
            return

        now_ts = time.time()
        if not hasattr(self, "_prewarmed_doc_ids"):
            self._prewarmed_doc_ids: set[int] = set()
            self._last_prewarm_reset_ts: float = now_ts

        # Làm mới lại link CDN mỗi 6 giờ (vì link Discord CDN có chữ ký hết hạn sau ~24h)
        if now_ts - getattr(self, "_last_prewarm_reset_ts", 0.0) >= 21600:
            self._prewarmed_doc_ids.clear()
            self._last_prewarm_reset_ts = now_ts

        rows = await self.bot.db.fetchall(
            "SELECT id, raw_text, page_count FROM documents_archive ORDER BY id DESC LIMIT 120"
        )
        if not rows:
            return

        batch_count = 0
        for r in rows:
            doc_id = int(r[0])
            if doc_id in self._prewarmed_doc_ids:
                continue
            raw_text = r[1] or ""
            page_count = r[2] or 0

            # 1. Phân giải và cache link CDN (doc_cdn_{id}) hoặc file_content_base64 lên Turso
            try:
                async with sess.get(f"{local_base}/api/documents/{doc_id}/file_url") as _:
                    pass
            except Exception:
                pass

            # 2. Nếu chưa có raw_text thì kích hoạt bóc tách 1 lần, nếu đã có thì đồng bộ sang Turso
            if len(raw_text.strip()) < 60:
                try:
                    async with sess.get(f"{local_base}/api/documents/{doc_id}/content") as _:
                        pass
                except Exception:
                    pass
            else:
                try:
                    await turso_db.execute(
                        "UPDATE documents_archive SET raw_text = ?, page_count = MAX(COALESCE(page_count, 0), ?) WHERE id = ? AND (raw_text IS NULL OR LENGTH(raw_text) < 60)",
                        raw_text,
                        page_count,
                        doc_id,
                    )
                except Exception:
                    pass

            self._prewarmed_doc_ids.add(doc_id)
            batch_count += 1
            if batch_count >= 2:
                break

    async def _process_turso_rpc_queue(self) -> None:
        """Xử lý các yêu cầu tương tác thời gian thực từ Vercel gửi qua bảng bot_rpc_queue trên Turso Cloud."""
        import json as _json
        import aiohttp as _aiohttp
        from database.turso_client import turso_db
        if not turso_db.is_configured:
            return

        rows = await turso_db.fetchall(
            "SELECT id, method, path, headers, body FROM bot_rpc_queue WHERE status = 'pending' ORDER BY id ASC LIMIT 5"
        )
        if not rows:
            return

        local_base = f"http://127.0.0.1:{settings.BOT_API_PORT}"
        secret = (getattr(settings, "BOT_API_SECRET", "") or "").strip()

        async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=25.0)) as sess:
            for r in rows:
                rpc_id = r.get("id")
                method = (r.get("method") or "POST").upper()
                path = r.get("path") or "/api/status"
                raw_headers = r.get("headers") or "{}"
                raw_body = r.get("body") or ""

                try:
                    req_headers = _json.loads(raw_headers) if raw_headers else {}
                except Exception:
                    req_headers = {}

                # Nếu Vercel đã xác thực quyền Admin/Secret, gắn X-Bot-Secret để thực thi nội bộ
                if req_headers.get("X-Vercel-Verified-Admin") == "1" and secret:
                    req_headers["X-Bot-Secret"] = secret
                req_headers["Content-Type"] = req_headers.get("Content-Type", "application/json")

                resp_status = 500
                resp_text = '{"error":"Internal RPC Error"}'
                try:
                    async with sess.request(
                        method,
                        f"{local_base}{path}",
                        headers=req_headers,
                        data=raw_body.encode("utf-8") if raw_body else None,
                    ) as resp:
                        resp_status = resp.status
                        resp_text = await resp.text()
                except Exception as exc:
                    resp_status = 502
                    resp_text = _json.dumps({"error": f"Bot RPC execution error: {exc}"}, ensure_ascii=False)

                await turso_db.execute(
                    """UPDATE bot_rpc_queue
                       SET status = 'done', response_status = ?, response_body = ?, updated_at = ?
                       WHERE id = ?""",
                    resp_status,
                    resp_text,
                    int(time.time()),
                    rpc_id,
                )

        # Dọn dẹp các lệnh RPC cũ hơn 10 phút để tiết kiệm dung lượng Turso
        await turso_db.execute("DELETE FROM bot_rpc_queue WHERE created_at < ?", int(time.time()) - 600)

    async def _turso_relay_loop(self) -> None:
        """Vòng lặp nền đồng bộ 2 chiều giữa Bot và Vercel thông qua Turso Cloud."""
        await self.bot.wait_until_ready()
        try:
            await self._init_turso_bridge_tables()
            logger.info("🌐 Đã kích hoạt cầu nối trực tiếp Bot <-> Vercel qua Turso Cloud (Zero-ngrok)!")
        except Exception as e:
            logger.warning(f"Lỗi khởi tạo bảng cầu nối Turso: {e}")

        last_snapshot = 0.0
        while not self.bot.is_closed():
            try:
                now = time.monotonic()
                if now - last_snapshot >= 20.0:
                    await self._push_turso_telemetry_snapshot()
                    last_snapshot = now
                await self._process_turso_rpc_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Lỗi vòng lặp Turso Relay: {e}")
            await asyncio.sleep(2.5)

    # =========================================================================
    # XÁC THỰC THÀNH VIÊN SERVER DISCORD & DIỄN ĐÀN 2 CHIỀU (WEB <-> DISCORD)
    # =========================================================================
    FORUM_CHANNEL_ID = 1535557885721841744
    FORUM_CATEGORIES = ("Góc thắc mắc", "Facts", "Hỏi đáp", "Ôn thi")

    async def handle_verify_member(self, request: web.Request) -> web.Response:
        """POST /api/account/verify-member: Xác thực tài khoản thành viên Server Orbit | Vietnam
        bằng Discord ID hoặc Username/Display Name để đăng nhập vào Orbit Hub & Diễn Đàn.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}

        identifier = str(body.get("identifier") or "").strip()
        if not identifier:
            return web.json_response(
                {"error": "Missing identifier", "message": "Vui lòng nhập Discord Username hoặc Discord ID của bạn."},
                status=400,
            )

        guild = self.bot.get_guild(DISCORD_GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            return web.json_response(
                {"error": "Guild unavailable", "message": "Bot đang kết nối tới máy chủ Discord, vui lòng thử lại sau vài giây."},
                status=503,
            )

        member = None
        clean_id = identifier.lstrip("<@!").rstrip(">").strip()
        if clean_id.isdigit():
            uid = int(clean_id)
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
        else:
            q_lower = identifier.lstrip("@").strip().lower()
            for m in guild.members:
                if (
                    m.name.lower() == q_lower
                    or (m.global_name and m.global_name.lower() == q_lower)
                    or m.display_name.lower() == q_lower
                ):
                    member = m
                    break
            if not member:
                try:
                    found = await guild.query_members(query=identifier.lstrip("@").strip(), limit=5)
                    if found:
                        member = found[0]
                except Exception:
                    member = None

        if not member or member.bot:
            return web.json_response(
                {
                    "error": "Member not found",
                    "message": (
                        f"Không tìm thấy thành viên '{identifier}' trong máy chủ Discord Orbit | Vietnam. "
                        "Hãy chắc chắn bạn đã tham gia server Discord Orbit và nhập đúng Username hoặc ID!"
                    ),
                },
                status=404,
            )

        avatar_url = (
            member.display_avatar.url
            if member.display_avatar
            else f"https://cdn.discordapp.com/embed/avatars/{int(member.id) % 5}.png"
        )
        roles = [r.name for r in member.roles if r.name != "@everyone"]

        return web.json_response(
            {
                "success": True,
                "user": {
                    "id": str(member.id),
                    "username": member.name,
                    "global_name": member.display_name or member.global_name or member.name,
                    "avatar": avatar_url,
                    "email": f"{member.name}@discord.orbit.vn",
                    "verified": True,
                    "roles": roles,
                    "connectedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            }
        )

    @staticmethod
    def _parse_forum_message_dict(m: dict) -> dict:
        """Chuẩn hóa tin nhắn Discord (bao gồm cả tin nhắn do Bot chuyển tiếp từ Web) thành cấu trúc chuẩn cho Web Forum."""
        raw_content = m.get("content") or ""
        author = m.get("author") or {}
        author_id = str(author.get("id") or "")
        author_name = author.get("global_name") or author.get("username") or "Thành viên Orbit"
        avatar_hash = author.get("avatar")
        if avatar_hash and author_id:
            author_avatar = f"https://cdn.discordapp.com/avatars/{author_id}/{avatar_hash}.png"
        else:
            author_avatar = "https://orbit-psi-black.vercel.app/server_icon.png"

        source = "discord"
        clean_content = raw_content

        # Nếu là bài đăng gốc hoặc phản hồi được gửi từ Orbit Web qua Bot
        web_reply_match = re.match(
            r"^💬 \*\*<@!?(\d+)> \(([^)]+)\)\*\* \*\(từ Orbit Web\)\*:\n([\s\S]*)$",
            raw_content,
        )
        web_starter_match = re.match(
            r"^🪐 \*\*Chuyên mục: ([^\n•]+) • Orbit Forum\*\*\n👤 \*\*Người đăng:\*\* ([^\n]+)\n(?:🖼️ \*\*Avatar:\*\* (https?://[^\s\n]+)\n)?━+\n([\s\S]*)$",
            raw_content,
        )

        if web_reply_match:
            author_id = web_reply_match.group(1)
            author_name = web_reply_match.group(2).strip()
            clean_content = web_reply_match.group(3).strip()
            source = "web"
        elif web_starter_match:
            raw_poster = web_starter_match.group(2).strip()
            custom_av = web_starter_match.group(3)
            clean_content = web_starter_match.group(4).strip()
            mention_m = re.search(r"<@!?(\d+)>\s*\(`?([^`)`]+)`?\)", raw_poster)
            if mention_m:
                author_id = mention_m.group(1)
                author_name = mention_m.group(2).strip()
                source = "web"
            else:
                author_name = re.sub(r"\s*\(`[^`]+`\)", "", raw_poster).strip()
            if custom_av:
                author_avatar = custom_av

        attachments = [
            {
                "id": str(a.get("id", "")),
                "filename": a.get("filename", "attachment"),
                "url": a.get("url", ""),
                "size": a.get("size", 0),
            }
            for a in (m.get("attachments") or [])
        ]

        return {
            "id": str(m.get("id", "")),
            "author_id": author_id,
            "author_name": author_name,
            "author_avatar": author_avatar,
            "content": clean_content,
            "created_at": m.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": source,
            "attachments": attachments,
        }

    async def _discord_rest(self, method: str, path: str, json_body: dict | None = None) -> tuple[int, Any]:
        """Gọi trực tiếp Discord REST API v10 bằng token của Bot."""
        import aiohttp as _aiohttp
        token = getattr(settings, "DISCORD_TOKEN", "") or os.getenv("DISCORD_TOKEN", "")
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }
        url = f"https://discord.com/api/v10{path}"
        async with _aiohttp.ClientSession(headers=headers, timeout=_aiohttp.ClientTimeout(total=12.0)) as s:
            async with s.request(method, url, json=json_body) as r:
                try:
                    data = await r.json()
                except Exception:
                    data = None
                return r.status, data

    async def handle_forum_get_threads(self, request: web.Request) -> web.Response:
        """GET /api/forum/threads: Lấy danh sách các bài thảo luận trong #💡・diễn-đàn đồng bộ với Discord."""
        st_ch, ch_data = await self._discord_rest("GET", f"/channels/{self.FORUM_CHANNEL_ID}")
        available_tags = (ch_data or {}).get("available_tags", []) if st_ch == 200 else []
        tag_id_to_name = {str(t["id"]): t["name"] for t in available_tags}

        st_act, act_data = await self._discord_rest("GET", f"/guilds/{DISCORD_GUILD_ID}/threads/active")
        active_threads = [
            t for t in ((act_data or {}).get("threads") or [])
            if str(t.get("parent_id")) == str(self.FORUM_CHANNEL_ID)
        ] if st_act == 200 else []

        st_arc, arc_data = await self._discord_rest("GET", f"/channels/{self.FORUM_CHANNEL_ID}/threads/archived/public")
        archived_threads = ((arc_data or {}).get("threads") or []) if st_arc == 200 else []

        seen_ids = set()
        raw_threads = []
        for t in active_threads + archived_threads:
            tid = str(t.get("id"))
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                raw_threads.append(t)

        # Lấy tin nhắn mở đầu (starter message) của từng thread song song để hiển thị preview + tác giả
        async def _enrich_thread(t: dict) -> dict:
            tid = str(t["id"])
            applied = [str(x) for x in (t.get("applied_tags") or [])]
            category = "Góc thắc mắc"
            for tag_id in applied:
                if tag_id in tag_id_to_name:
                    category = tag_id_to_name[tag_id]
                    break
            # Chuẩn hóa tên chuyên mục nếu nằm trong tiêu đề [Facts], [Hỏi đáp], [Ôn thi], [Góc thắc mắc]
            t_name = t.get("name") or "Chủ đề thảo luận"
            for cat_name in self.FORUM_CATEGORIES:
                if t_name.lower().startswith(f"[{cat_name.lower()}]"):
                    category = cat_name
                    break

            st_m, msgs = await self._discord_rest("GET", f"/channels/{tid}/messages?limit=2")
            starter_parsed = None
            if st_m == 200 and isinstance(msgs, list) and msgs:
                # Tin nhắn đầu tiên của thread có id == tid hoặc phần tử cuối nếu ít tin nhắn
                starter_raw = next((m for m in msgs if str(m.get("id")) == tid), msgs[-1])
                starter_parsed = self._parse_forum_message_dict(starter_raw)

            msg_count = int(t.get("message_count") or t.get("total_message_sent") or 1)
            created_ts = (
                starter_parsed["created_at"]
                if starter_parsed
                else (t.get("thread_metadata") or {}).get("create_timestamp")
                or datetime.datetime.now(datetime.timezone.utc).isoformat()
            )

            return {
                "id": tid,
                "title": t_name,
                "category": category,
                "author_id": starter_parsed["author_id"] if starter_parsed else str(t.get("owner_id", "")),
                "author_name": starter_parsed["author_name"] if starter_parsed else "Thành viên Orbit",
                "author_avatar": starter_parsed["author_avatar"] if starter_parsed else "https://orbit-psi-black.vercel.app/server_icon.png",
                "excerpt": (starter_parsed["content"][:220] if starter_parsed else ""),
                "message_count": max(1, msg_count),
                "reply_count": max(0, msg_count - 1),
                "created_at": created_ts,
                "jump_url": f"https://discord.com/channels/{DISCORD_GUILD_ID}/{tid}",
            }

        enriched = await asyncio.gather(*[_enrich_thread(t) for t in raw_threads[:25]])
        enriched_list = sorted(enriched, key=lambda x: int(x["id"]), reverse=True)

        return web.json_response(
            {
                "channel_id": str(self.FORUM_CHANNEL_ID),
                "channel_name": "💡・diễn-đàn",
                "categories": list(self.FORUM_CATEGORIES),
                "threads": enriched_list,
            }
        )

    async def handle_forum_get_thread_detail(self, request: web.Request) -> web.Response:
        """GET /api/forum/threads/{thread_id}: Lấy chi tiết chủ đề và toàn bộ tin nhắn đồng bộ với Discord."""
        thread_id = request.match_info.get("thread_id", "").strip()
        if not thread_id.isdigit():
            return web.json_response({"error": "Invalid thread_id"}, status=400)

        st_t, t_data = await self._discord_rest("GET", f"/channels/{thread_id}")
        if st_t != 200 or not isinstance(t_data, dict):
            return web.json_response({"error": "Thread not found"}, status=404)

        st_ch, ch_data = await self._discord_rest("GET", f"/channels/{self.FORUM_CHANNEL_ID}")
        available_tags = (ch_data or {}).get("available_tags", []) if st_ch == 200 else []
        tag_id_to_name = {str(t["id"]): t["name"] for t in available_tags}

        applied = [str(x) for x in (t_data.get("applied_tags") or [])]
        category = "Góc thắc mắc"
        for tag_id in applied:
            if tag_id in tag_id_to_name:
                category = tag_id_to_name[tag_id]
                break

        st_m, raw_msgs = await self._discord_rest("GET", f"/channels/{thread_id}/messages?limit=100")
        messages = []
        if st_m == 200 and isinstance(raw_msgs, list):
            # Discord trả về tin nhắn từ mới nhất -> cũ nhất, đảo ngược lại theo thứ tự thời gian
            for rm in reversed(raw_msgs):
                parsed = self._parse_forum_message_dict(rm)
                if parsed["content"] or parsed["attachments"]:
                    messages.append(parsed)

        return web.json_response(
            {
                "id": str(t_data.get("id")),
                "title": t_data.get("name") or "Chủ đề thảo luận",
                "category": category,
                "jump_url": f"https://discord.com/channels/{DISCORD_GUILD_ID}/{thread_id}",
                "messages": messages,
            }
        )

    async def handle_forum_create_thread(self, request: web.Request) -> web.Response:
        """POST /api/forum/threads: Đăng chủ đề mới từ Web -> Bot tự động tạo bài mới trong #💡・diễn-đàn trên Discord."""
        try:
            body = await request.json()
        except Exception:
            body = {}

        title = str(body.get("title") or "").strip()
        content = str(body.get("content") or "").strip()
        category = str(body.get("category") or "Góc thắc mắc").strip()
        author_id = str(body.get("author_id") or "").strip()
        author_name = str(body.get("author_name") or "Thành viên Orbit").strip()
        author_avatar = str(body.get("author_avatar") or "").strip()

        if category not in self.FORUM_CATEGORIES:
            category = "Góc thắc mắc"
        if len(title) < 4:
            return web.json_response(
                {"error": "Invalid title", "message": "Tiêu đề bài viết cần tối thiểu 4 ký tự."},
                status=400,
            )
        if len(content) < 4:
            return web.json_response(
                {"error": "Invalid content", "message": "Nội dung bài viết cần tối thiểu 4 ký tự."},
                status=400,
            )

        # Lấy tag ID tương ứng trên kênh #💡・diễn-đàn
        st_ch, ch_data = await self._discord_rest("GET", f"/channels/{self.FORUM_CHANNEL_ID}")
        available_tags = (ch_data or {}).get("available_tags", []) if st_ch == 200 else []
        tag_id = None
        for t in available_tags:
            if t.get("name", "").lower() == category.lower():
                tag_id = str(t["id"])
                break

        full_title = title if title.startswith("[") else f"[{category}] {title}"
        poster_str = f"<@{author_id}> (`{author_name}`)" if author_id.isdigit() else f"**{author_name}**"
        discord_content = (
            f"🪐 **Chuyên mục: {category} • Orbit Forum**\n"
            f"👤 **Người đăng:** {poster_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{content}"
        )

        payload: dict[str, Any] = {
            "name": full_title[:100],
            "auto_archive_duration": 10080,
            "message": {
                "content": discord_content[:1950],
                "allowed_mentions": {"parse": []},
            },
        }
        if tag_id:
            payload["applied_tags"] = [tag_id]

        st_create, created = await self._discord_rest("POST", f"/channels/{self.FORUM_CHANNEL_ID}/threads", payload)
        if st_create not in (200, 201) or not isinstance(created, dict):
            return web.json_response(
                {"error": "Discord error", "message": "Không thể tạo bài viết trên kênh Discord #💡・diễn-đàn."},
                status=502,
            )

        tid = str(created.get("id"))
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        starter_msg = {
            "id": tid,
            "author_id": author_id,
            "author_name": author_name,
            "author_avatar": author_avatar or "https://orbit-psi-black.vercel.app/server_icon.png",
            "content": content,
            "created_at": now_iso,
            "source": "web",
            "attachments": [],
        }

        return web.json_response(
            {
                "success": True,
                "thread": {
                    "id": tid,
                    "title": full_title[:100],
                    "category": category,
                    "author_id": author_id,
                    "author_name": author_name,
                    "author_avatar": author_avatar or "https://orbit-psi-black.vercel.app/server_icon.png",
                    "excerpt": content[:220],
                    "message_count": 1,
                    "reply_count": 0,
                    "created_at": now_iso,
                    "jump_url": f"https://discord.com/channels/{DISCORD_GUILD_ID}/{tid}",
                    "messages": [starter_msg],
                },
            },
            status=201,
        )

    async def handle_forum_post_message(self, request: web.Request) -> web.Response:
        """POST /api/forum/threads/{thread_id}/messages: Gửi tin nhắn phản hồi từ Web -> đồng bộ ngay vào Thread Discord."""
        thread_id = request.match_info.get("thread_id", "").strip()
        if not thread_id.isdigit():
            return web.json_response({"error": "Invalid thread_id"}, status=400)

        try:
            body = await request.json()
        except Exception:
            body = {}

        content = str(body.get("content") or "").strip()
        author_id = str(body.get("author_id") or "").strip()
        author_name = str(body.get("author_name") or "Thành viên Orbit").strip()
        author_avatar = str(body.get("author_avatar") or "").strip()

        if not content:
            return web.json_response(
                {"error": "Empty message", "message": "Nội dung tin nhắn không được để trống."},
                status=400,
            )

        uid_tag = author_id if author_id.isdigit() else "0"
        discord_msg_text = f"💬 **<@{uid_tag}> ({author_name})** *(từ Orbit Web)*:\n{content[:1850]}"

        st_post, posted = await self._discord_rest(
            "POST",
            f"/channels/{thread_id}/messages",
            {
                "content": discord_msg_text,
                "allowed_mentions": {"parse": []},
            },
        )
        if st_post not in (200, 201) or not isinstance(posted, dict):
            return web.json_response(
                {"error": "Discord error", "message": "Không thể gửi tin nhắn vào chủ đề Discord."},
                status=502,
            )

        return web.json_response(
            {
                "success": True,
                "message": {
                    "id": str(posted.get("id", int(time.time() * 1000))),
                    "author_id": author_id,
                    "author_name": author_name,
                    "author_avatar": author_avatar or "https://orbit-psi-black.vercel.app/server_icon.png",
                    "content": content,
                    "created_at": posted.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "source": "web",
                    "attachments": [],
                },
            },
            status=201,
        )

    async def stop(self) -> None:
        """Dừng HTTP Server an toàn."""
        if getattr(self, "_turso_relay_task", None) and not self._turso_relay_task.done():
            self._turso_relay_task.cancel()
        if self.runner:
            await self.runner.cleanup()
            logger.info("Đã dừng Bot API Bridge.")
