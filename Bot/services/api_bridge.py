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
        self.app = web.Application(
            client_max_size=30 * 1024 * 1024,  # Giới hạn an toàn 30 MB
            middlewares=[self._rate_limit_middleware, self._cors_middleware, self._auth_middleware],
        )
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._setup_routes()

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

        # 1. Khóa bí mật BOT_API_SECRET luôn có toàn quyền quản trị cao nhất
        if token and token == settings.BOT_API_SECRET:
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
        allowed_origins = [
            "https://hyperhub-one.vercel.app",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
        ]
        if req_origin in allowed_origins or (req_origin and req_origin.endswith(".vercel.app")):
            response.headers["Access-Control-Allow-Origin"] = req_origin
            response.headers["Vary"] = "Origin"
        else:
            response.headers["Access-Control-Allow-Origin"] = "https://hyperhub-one.vercel.app"

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD, DELETE, PATCH, PUT"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Bot-Secret, ngrok-skip-browser-warning"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler: Any) -> web.Response:
        """Kiểm tra token cho các endpoint POST, DELETE, PATCH, PUT / yêu cầu bảo mật."""
        if request.method in ("POST", "DELETE", "PATCH", "PUT"):
            # Endpoint upload, import_gdrive, notify, account/link và admin endpoints sẽ tự kiểm tra xác thực bên trong handler
            if (
                request.path in ("/api/documents/upload", "/api/documents/import_gdrive", "/api/notify", "/api/account/link")
                or request.path.startswith("/api/admin/")
            ):
                return await handler(request)

            auth_header = request.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif "X-Bot-Secret" in request.headers:
                token = request.headers["X-Bot-Secret"].strip()

            if token != settings.BOT_API_SECRET:
                return web.json_response(
                    {"error": "Unauthorized", "message": "Sai mã khóa bí mật BOT_API_SECRET"},
                    status=401,
                )
        return await handler(request)

    def _setup_routes(self) -> None:
        """Đăng ký các API endpoints."""
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/leaderboard", self.handle_leaderboard)
        self.app.router.add_get("/api/duels/active", self.handle_active_duels)
        self.app.router.add_get("/api/user/{discord_id}", self.handle_user_profile)
        self.app.router.add_post("/api/notify", self.handle_notify)
        self.app.router.add_post("/api/account/link", self.handle_account_link)
        self.app.router.add_get("/api/account/me", self.handle_account_me)
        # Endpoints Kho Tài Liệu & Đề Thi
        self.app.router.add_get("/api/documents", self.handle_get_documents)
        self.app.router.add_get("/api/documents/stats", self.handle_document_stats)
        self.app.router.add_get("/api/documents/request_exam", self.handle_request_exam)
        self.app.router.add_get("/api/documents/random", self.handle_request_exam)
        self.app.router.add_get("/api/documents/{id}/download", self.handle_download_document)
        self.app.router.add_get("/api/documents/{id}/file_url", self.handle_get_document_file_url)
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
        if not token or token == settings.BOT_API_SECRET:
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
        if not token or token == settings.BOT_API_SECRET:
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
        secret_ok = bool(token) and token == settings.BOT_API_SECRET
        if "X-Bot-Secret" in request.headers and request.headers["X-Bot-Secret"].strip() == settings.BOT_API_SECRET:
            secret_ok = True

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
        try:
            limit = min(max(int(query_params.get("limit", 20)), 1), 100)
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

        # Map min_id và count cho từng hash / tên file để xác định bản gốc vs bản trùng
        min_id_rows = await self.bot.db.fetchall("""
            SELECT COALESCE(NULLIF(file_hash, ''), LOWER(file_name)), MIN(id), COUNT(*)
            FROM documents_archive
            GROUP BY COALESCE(NULLIF(file_hash, ''), LOWER(file_name))
        """)
        doc_stats_map = {r[0]: (r[1], r[2]) for r in min_id_rows if r[0]}

        base_cols = (
            "id, subject, title, file_name, file_size_bytes, file_type, estimated_level,"
            "question_count, page_count, author_name, jump_url, timestamp, file_hash, notes"
        )
        scan_cols = "verdict, exam_track, confidence"
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
            # DB cũ chưa migrate verdict/track/confidence
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
                "notes": r[13] if len(r) > 13 and r[13] else "",
                "verdict": r[14] if has_scan and len(r) > 14 else None,
                "exam_track": r[15] if has_scan and len(r) > 15 else None,
                "confidence": r[16] if has_scan and len(r) > 16 else None,
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
        """GET /api/documents/stats: Thống kê kho tài liệu (Tổng số thực tế, đề độc bản & đề trùng)."""
        if not hasattr(self.bot, "db"):
            return web.json_response({"error": "Cơ sở dữ liệu chưa sẵn sàng"}, status=503)

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

        return web.json_response({
            "success": True,
            "total_items": total_items,
            "total_real": total_items,
            "unique_items": unique_items,
            "duplicate_items": duplicate_items,
            "total_bytes": total_bytes,
            "subjects": subjects,
        })

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
        secret_ok = bool(token) and token == settings.BOT_API_SECRET
        if "X-Bot-Secret" in request.headers and request.headers["X-Bot-Secret"].strip() == settings.BOT_API_SECRET:
            secret_ok = True

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
                    "message": "Bạn phải tham gia Discord Server HyperHub mới được lấy đề thi.",
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
                "notes": row[13] if len(row) > 13 and row[13] else "",
                "verdict": row[14] if has_scan and len(row) > 14 else None,
                "exam_track": row[15] if has_scan and len(row) > 15 else None,
                "confidence": row[16] if has_scan and len(row) > 16 else None,
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

        # Thử lấy file từ local nếu nộp từ web
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        safe_file_name = os.path.basename(file_name).replace("..", "").strip()
        local_file = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{safe_file_name}"))
        real_upload_dir = os.path.realpath(upload_dir)
        if not direct_url and local_file.startswith(real_upload_dir + os.sep) and os.path.exists(local_file):
            direct_url = f"/api/documents/{doc_id}/download"

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
            "jump_url": jump_url,
        })

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
        if token == settings.BOT_API_SECRET:
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

        # 1. Tính SHA-256 hash của tệp
        file_hash = None
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

        # 3. Chạy DocInspector phân tích nội dung tệp
        detected_subject = custom_subject or "MATHEMATICS"
        detected_grade = custom_grade or "Chung ( chung cho tất cả khối )"
        exam_type_str = "THI_THU_THPT"
        confidence = 0.95
        question_count = 0
        page_count = 1
        raw_text_summary = ""
        academic_year = None
        school_name = None

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
                if hasattr(report, "pass1") and report.pass1:
                    question_count = getattr(report.pass1, "question_count", 0)
                    page_count = getattr(report.pass1, "page_count", 1)
        except Exception as e:
            logger.warning(f"Lỗi khi chạy DocInspector: {e}")

        # 4. Lưu tệp lên ổ đĩa local để phục vụ tải về / xem trước
        upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        file_ext = os.path.splitext(file_name)[1].lower().replace(".", "").upper() or "PDF"

        # 5. Lưu vào database documents_archive
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
            0,
            0,
            "https://hyperhub-one.vercel.app/#vault",
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
        if token != settings.BOT_API_SECRET:
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
                "not_member": "Bạn chưa tham gia Discord Server HyperHub. Hãy vào server rồi thử lại.",
                "not_admin": "Tài khoản của bạn không có role Quản trị (Owner / Co-Owner / Administrator / Moderator).",
            }
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

    async def stop(self) -> None:
        """Dừng HTTP Server an toàn."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Đã dừng Bot API Bridge.")
