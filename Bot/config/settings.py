"""Configuration loader and validator for Discord Competitive Programming Bot."""

import os

try:
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseSettings = object


if HAS_PYDANTIC:

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        DISCORD_TOKEN: str = Field(default="", description="Discord bot token")
        OWNER_ID: int = Field(default=0, description="Discord ID of the bot owner")
        CATEGORY_ID: int = Field(
            default=0,
            description="ID Thư mục / Category Channel (・━━ ❓GIẢI ĐỀ/CÂU HỎI ━━・)",
        )
        CHON_ID: int = Field(
            default=0, description="Kênh #📤・mode (Giải thích 2 chế độ làm bài)"
        )
        BAITAP_ID: int = Field(
            default=0,
            description="Kênh #📋・contest (Danh mục cuộc thi & bài tập theo Div/Tier)",
        )
        RANKED_CHANNEL_ID: int = Field(
            default=0, description="Kênh #📋・ranked (Dành cho thi đấu Ranked)"
        )
        UP_RANK: int = Field(
            default=0,
            description="Kênh #✅・leaderboard (Bảng xếp hạng Top 50 toàn Server)",
        )
        CF_ID: int = Field(
            default=0,
            description="Kênh #✅・accounts (Hướng dẫn & liên kết Codeforces)",
        )
        SUBMIT_ID: int = Field(
            default=0,
            description="Kênh #📤・submit (Trạm nộp bài trực tiếp không cần lệnh)",
        )
        WINNER_CHANNEL_ID: int = Field(
            default=0,
            description="Kênh #🏆・winner (Thông báo vinh danh người chiến thắng Ranked 1:1)",
        )
        DOC_INTAKE_CHANNEL_ID: int = Field(
            default=1535278288828633138,
            description="Kênh nộp tài liệu — bot tự động nhận file/link & phân loại",
        )
        DOC_CATEGORY_ID: int = Field(
            default=1534147951797080174,
            description="Thư mục phân loại tài liệu (Classification Category)",
        )
        DOC_SEARCH_CHANNEL_ID: int = Field(
            default=1553678782101979186,
            description="Kênh tra cứu kho tài liệu học tập & đề thi",
        )
        DUEL_LOG_CHANNEL_ID: int = Field(
            default=1536199276273860638,
            description="Kênh nhật ký lưu trữ lịch sử đấu, transcript và báo cáo chống gian lận Ranked 1:1",
        )
        PROBLEM_ARCHIVE_CHANNEL_ID: int = Field(
            default=1548627763467128912,
            description="Kênh lưu trữ đề bài, lời giải và code mẫu tự động sau mỗi bài Freedom/Ranked",
        )
        # ==================== HYPER GENERATOR & EXAM PLATFORM ====================
        GENERATE_CHANNEL_ID: int = Field(
            default=1550896415046377615,
            description="Kênh #📄・generate (Bảng điều khiển & Ticket tạo đề AI)",
        )
        INFO_CHANNEL_ID: int = Field(
            default=1550896576636129320,
            description="Kênh #📄・info (Sổ tay hướng dẫn & bảng giá Gói Hyper)",
        )
        DATABASE_ARCHIVE_CHANNEL_ID: int = Field(
            default=1548627763467128912,
            description="Kênh #database (Kho lưu trữ đề thi, lời giải và tài liệu)",
        )
        CHUNK_ARCHIVE_CHANNEL_ID: int = Field(
            default=0,
            description="Kênh chứa các phần file chẻ nhỏ (0 = tự tạo #file-chunks)",
        )
        ARCHIVE_CHUNK_MB: int = Field(
            default=25,
            description="Dung lượng tối đa mỗi phần chẻ (MB) khi offload file lớn lên Discord (nâng theo Nitro boost)",
        )
        ROLE_HYPER_ELITE_ID: int = Field(
            default=1550901268392972299,
            description="Role Gói Hyper Elite (VVIP - Vô hạn Token)",
        )
        ROLE_HYPER_ULTRA_ID: int = Field(
            default=1550901272943657061,
            description="Role Gói Hyper Ultra (2,800 Token/ngày)",
        )
        ROLE_HYPER_PRO_ID: int = Field(
            default=1550901276689039431,
            description="Role Gói Hyper Pro (700 Token/ngày)",
        )
        ROLE_HYPER_FREE_ID: int = Field(
            default=1550901280656859246,
            description="Role Gói Hyper Free (200 Token/ngày)",
        )
        ROLE_DIVIDER_ID: int = Field(
            default=1550901263154020504,
            description="Role phân cách: ╭─── GÓI HYPER ───╮",
        )
        RANKED_HIDDEN_CATEGORY_IDS: list[int] = Field(
            default=[1534147161091211414, 1534147951797080174, 1534148003701719070],
            description="Danh mục kênh bị ẩn tạm thời đối với thí sinh khi đang thi đấu Ranked (Cộng Đồng, Tài Liệu, Voice Chat)",
        )
        GIAM_KHAO_ROLE_ID: int = Field(
            default=0,
            description="Role Giám Khảo / Moderator được phép quan sát trận đấu Ranked 1:1",
        )
        GIAM_KHAO: int = Field(
            default=0,
            description="Alias cho GIAM_KHAO_ROLE_ID",
        )

        LOGO_ID: str = Field(
            default="https://assets.codeforces.com/favicon-96x96.png",
            description="Bot logo URL for all rich embeds (1:1 square centered)",
        )

        # Role Thành viên mặc định cho tất cả mọi người (🌱 Học sinh)
        MEMBER_ROLE_ID: int = Field(
            default=0,
            description="ID của Role Thành Viên Mặc Định (🌱 Học sinh) tự động cấp cho mọi người",
        )

        # Role Test dự phòng cho tương lai
        TEST_ROLE_ID: int = Field(
            default=0,
            description="ID của Role Test (🧪 Test) dự phòng",
        )

        # ==================== RETIRED ====================
        R_ID: int = Field(
            default=0,
            description="ID của Role 'Giải Nghệ' (RHT1) dành cho cựu thí sinh",
        )

        # ==================== FREEDOM ROLES ====================
        HT1_FREEDOM_ROLE_ID: int = Field(default=0, description="HT1 Freedom (>= 3000)")
        MT1_FREEDOM_ROLE_ID: int = Field(
            default=0, description="MT1 Freedom (2600-2999)"
        )
        LT1_FREEDOM_ROLE_ID: int = Field(
            default=0, description="LT1 Freedom (2400-2599)"
        )
        HT2_FREEDOM_ROLE_ID: int = Field(
            default=0, description="HT2 Freedom (2300-2399)"
        )
        MT2_FREEDOM_ROLE_ID: int = Field(
            default=0, description="MT2 Freedom (2100-2299)"
        )
        LT2_FREEDOM_ROLE_ID: int = Field(
            default=0, description="LT2 Freedom (1900-2099)"
        )
        T3_FREEDOM_ROLE_ID: int = Field(default=0, description="T3 Freedom (1600-1899)")
        T4_FREEDOM_ROLE_ID: int = Field(default=0, description="T4 Freedom (1400-1599)")
        T5_FREEDOM_ROLE_ID: int = Field(default=0, description="T5 Freedom (1200-1399)")
        T6_FREEDOM_ROLE_ID: int = Field(default=0, description="T6 Freedom (700-1199)")
        T7_FREEDOM_ROLE_ID: int = Field(default=0, description="T7 Freedom (400-699)")
        T8_FREEDOM_ROLE_ID: int = Field(default=0, description="T8 Freedom (< 400)")

        # ==================== RANKED ROLES ====================
        HT1_RANKED_ROLE_ID: int = Field(default=0, description="HT1 Ranked (>= 3000)")
        MT1_RANKED_ROLE_ID: int = Field(default=0, description="MT1 Ranked (2600-2999)")
        LT1_RANKED_ROLE_ID: int = Field(default=0, description="LT1 Ranked (2400-2599)")
        HT2_RANKED_ROLE_ID: int = Field(default=0, description="HT2 Ranked (2300-2399)")
        MT2_RANKED_ROLE_ID: int = Field(default=0, description="MT2 Ranked (2100-2299)")
        LT2_RANKED_ROLE_ID: int = Field(default=0, description="LT2 Ranked (1900-2099)")
        T3_RANKED_ROLE_ID: int = Field(default=0, description="T3 Ranked (1600-1899)")
        T4_RANKED_ROLE_ID: int = Field(default=0, description="T4 Ranked (1400-1599)")
        T5_RANKED_ROLE_ID: int = Field(default=0, description="T5 Ranked (1200-1399)")
        T6_RANKED_ROLE_ID: int = Field(default=0, description="T6 Ranked (700-1199)")
        T7_RANKED_ROLE_ID: int = Field(default=0, description="T7 Ranked (400-699)")
        T8_RANKED_ROLE_ID: int = Field(default=0, description="T8 Ranked (< 400)")

        # Legacy aliases
        HT1_ROLE_ID: int = Field(default=0, description="High Tier 1 (>= 3000)")
        MT1_ROLE_ID: int = Field(default=0, description="Mid Tier 1 (2600-2999)")
        LT1_ROLE_ID: int = Field(default=0, description="Low Tier 1 (2400-2599)")
        HT2_ROLE_ID: int = Field(default=0, description="High Tier 2 (2300-2399)")
        MT2_ROLE_ID: int = Field(default=0, description="Mid Tier 2 (2100-2299)")
        LT2_ROLE_ID: int = Field(default=0, description="Low Tier 2 (1900-2099)")
        T3_ROLE_ID: int = Field(default=0, description="Tier 3 (1600-1899)")
        T4_ROLE_ID: int = Field(default=0, description="Tier 4 (1400-1599)")
        T5_ROLE_ID: int = Field(default=0, description="Tier 5 (1200-1399)")
        T6_ROLE_ID: int = Field(default=0, description="Tier 6 (700-1199)")
        T7_ROLE_ID: int = Field(default=0, description="Tier 7 (400-699)")
        T8_ROLE_ID: int = Field(default=0, description="Tier 8 (< 400)")

        DATABASE_URL: str = Field(
            default="sqlite+aiosqlite:///bot.db",
            description="Async SQLAlchemy database URL",
        )

        CF_API_KEY: str | None = Field(default=None, description="Codeforces API Key")
        CF_API_SECRET: str | None = Field(
            default=None, description="Codeforces API Secret"
        )
        CF_SYNC_INTERVAL_SECONDS: int = Field(
            default=45, description="Interval in seconds for CF sync"
        )

        JUDGE_TIMEOUT: int = Field(
            default=5, description="Timeout in seconds per test case"
        )
        JUDGE_MEMORY_LIMIT: int = Field(
            default=256, description="Memory limit in Megabytes"
        )
        JUDGE_CPU_LIMIT: float = Field(default=2.0, description="CPU cores limit")
        JUDGE_PIDS_LIMIT: int = Field(
            default=64, description="Max processes in sandbox"
        )
        DOCKER_SANDBOX_IMAGE: str = Field(
            default="cp-sandbox:latest", description="Docker image tag"
        )
        USE_DOCKER_SANDBOX: bool = Field(
            default=True, description="Whether to run in Docker container"
        )

        MAX_CODE_LENGTH: int = Field(
            default=65536, description="Max code characters (64 KB)"
        )
        SUBMIT_COOLDOWN_SECONDS: int = Field(
            default=15, description="Submission cooldown in seconds"
        )
        AI_SUSPICION_THRESHOLD: int = Field(
            default=65, description="Threshold (0-100) to flag AI code"
        )
        AI_MODEL: str = Field(
            default="qwen3.5:4b", description="Central AI Core & Problem Generator Model Name"
        )
        AI_BACKUP_MODEL: str = Field(
            default="qwen3.5:2b", description="Backup AI Core Model Name"
        )
        AI_VERIFIER_MODEL: str = Field(
            default="gemma3:4b", description="AI Model for Problem Verification & Logic Enhancement"
        )
        OLLAMA_BASE_URL: str = Field(
            default="http://localhost:11434", description="Ollama local server endpoint"
        )
        OLLAMA_MODEL: str = Field(
            default="qwen3.5:4b", description="Local AI model for problem generation & AI Core"
        )
        OLLAMA_TIMEOUT: int = Field(
            default=1800, description="Ollama API request timeout in seconds (30 phut)"
        )
        OLLAMA_NUM_GPU: int = Field(
            default=0,
            description="So layer offload len GPU (0 = auto, 999 = ep full GPU)",
        )
        HSA_OVERRIDE_GFX_VERSION: str | None = Field(
            default=None,
            description="AMD ROCm GFX override (vd: 10.3.0 cho RDNA2, 11.0.0 cho RDNA3)",
        )
        AI_CORE_CHANNEL_ID: int = Field(
            default=1544356764240183358, description="AI Core Control Channel ID"
        )
        AI_CHAT_CHANNEL_ID: int = Field(
            default=0, description="AI Chat Channel ID (0 = disabled)"
        )
        LINK_SCANNER_CHANNEL_ID: int = Field(
            default=1546522680638054461,
            description="Kênh kiểm tra an toàn & quét virus link (1546522680638054461)",
        )
        VIRUSTOTAL_API_KEY: str = Field(
            default="",
            description="API Key VirusTotal v3 (tùy chọn)",
        )
        GOOGLE_SAFE_BROWSING_API_KEY: str = Field(
            default="",
            description="Google Safe Browsing API Key (tùy chọn)",
        )
        CONFLICT_MONITOR_CATEGORY_ID: int = Field(
            default=1534147161091211414,
            description="ID Thư mục (Category ID) giám sát xung đột",
        )
        CONFLICT_AI_MODEL: str = Field(
            default="qwen2.5:0.5b",
            description="Mô hình AI siêu nhẹ phân tích xung đột",
        )
        CONFLICT_MUTE_DURATION_MINUTES: int = Field(
            default=5,
            description="Thời gian timeout mặc định khi phát hiện gây gổ (phút)",
        )
        ANTI_RAID_ENABLED: bool = Field(
            default=True,
            description="Bật/Tắt hệ thống chống raid bot và join flood",
        )
        ANTI_SPAM_ENABLED: bool = Field(
            default=True,
            description="Bật/Tắt hệ thống chống spam tin nhắn tự động",
        )
        ANTI_NUKE_AUTO_RESTORE: bool = Field(
            default=True,
            description="Tự động khôi phục cấu trúc server 100% khi phát hiện phá hoại",
        )
        BACKUP_AUTO_INTERVAL_HOURS: int = Field(
            default=6,
            description="Chu kỳ tự động tạo snapshot cấu trúc server (giờ)",
        )
        JOIN_FLOOD_THRESHOLD: int = Field(
            default=5,
            description="Ngưỡng phát hiện join flood (số tài khoản trong 10s)",
        )
        MESSAGE_FLOOD_THRESHOLD: int = Field(
            default=5,
            description="Ngưỡng phát hiện spam tin nhắn (số tin trong 4s)",
        )
        LOG_LEVEL: str = Field(
            default="INFO", description="Console & file logging level"
        )

        # ==================== BOT & WEB API BRIDGE ====================
        BOT_API_ENABLED: bool = Field(
            default=True,
            description="Kích hoạt API Bridge HTTP/REST để kết nối Web với Bot",
        )
        BOT_API_HOST: str = Field(
            default="0.0.0.0",
            description="Host lắng nghe của Bot API Bridge",
        )
        BOT_API_PORT: int = Field(
            default=8080,
            description="Cổng (Port) của Bot API Bridge",
        )
        BOT_API_SECRET: str = Field(
            default="hyperhub_bridge_secret_key_2026",
            description="Mã khóa bí mật (Bearer/Header Secret) xác thực giữa Bot và Web",
        )

        @field_validator("DATABASE_URL")
        @classmethod
        def validate_database_url(cls, v: str) -> str:
            if v.startswith("sqlite:///"):
                return v.replace("sqlite:///", "sqlite+aiosqlite:///")
            if v.startswith("postgresql://"):
                return v.replace("postgresql://", "postgresql+asyncpg://")
            return v

        def get_freedom_role_id_for_rank(self, rank_name: str) -> int | None:
            """Trả về ID của Role Freedom tương ứng với Bậc Rank."""
            mapping: dict[str, int] = {
                "HT1": self.HT1_FREEDOM_ROLE_ID or self.HT1_ROLE_ID,
                "MT1": self.MT1_FREEDOM_ROLE_ID or self.MT1_ROLE_ID,
                "LT1": self.LT1_FREEDOM_ROLE_ID or self.LT1_ROLE_ID,
                "HT2": self.HT2_FREEDOM_ROLE_ID or self.HT2_ROLE_ID,
                "MT2": self.MT2_FREEDOM_ROLE_ID or self.MT2_ROLE_ID,
                "LT2": self.LT2_FREEDOM_ROLE_ID or self.LT2_ROLE_ID,
                "T3": self.T3_FREEDOM_ROLE_ID or self.T3_ROLE_ID,
                "T4": self.T4_FREEDOM_ROLE_ID or self.T4_ROLE_ID,
                "T5": self.T5_FREEDOM_ROLE_ID or self.T5_ROLE_ID,
                "T6": self.T6_FREEDOM_ROLE_ID or self.T6_ROLE_ID,
                "T7": self.T7_FREEDOM_ROLE_ID or self.T7_ROLE_ID,
                "T8": self.T8_FREEDOM_ROLE_ID or self.T8_ROLE_ID,
            }
            role_id = mapping.get(rank_name.upper())
            return role_id if role_id and role_id > 0 else None

        def get_all_freedom_rank_role_ids(self) -> list[int]:
            """Trả về danh sách ID tất cả các Role Freedom."""
            roles = [
                self.HT1_FREEDOM_ROLE_ID,
                self.MT1_FREEDOM_ROLE_ID,
                self.LT1_FREEDOM_ROLE_ID,
                self.HT2_FREEDOM_ROLE_ID,
                self.MT2_FREEDOM_ROLE_ID,
                self.LT2_FREEDOM_ROLE_ID,
                self.T3_FREEDOM_ROLE_ID,
                self.T4_FREEDOM_ROLE_ID,
                self.T5_FREEDOM_ROLE_ID,
                self.T6_FREEDOM_ROLE_ID,
                self.T7_FREEDOM_ROLE_ID,
                self.T8_FREEDOM_ROLE_ID,
            ]
            return list({r for r in roles if r > 0})

        def get_ranked_role_id_for_rank(self, rank_name: str) -> int | None:
            """Trả về ID của Role Ranked 1:1 tương ứng với Bậc Rank."""
            mapping: dict[str, int] = {
                "HT1": self.HT1_RANKED_ROLE_ID,
                "MT1": self.MT1_RANKED_ROLE_ID,
                "LT1": self.LT1_RANKED_ROLE_ID,
                "HT2": self.HT2_RANKED_ROLE_ID,
                "MT2": self.MT2_RANKED_ROLE_ID,
                "LT2": self.LT2_RANKED_ROLE_ID,
                "T3": self.T3_RANKED_ROLE_ID,
                "T4": self.T4_RANKED_ROLE_ID,
                "T5": self.T5_RANKED_ROLE_ID,
                "T6": self.T6_RANKED_ROLE_ID,
                "T7": self.T7_RANKED_ROLE_ID,
                "T8": self.T8_RANKED_ROLE_ID,
            }
            role_id = mapping.get(rank_name.upper())
            return role_id if role_id and role_id > 0 else None

        def get_all_ranked_role_ids(self) -> list[int]:
            """Trả về danh sách ID tất cả các Role Ranked."""
            roles = [
                self.HT1_RANKED_ROLE_ID,
                self.MT1_RANKED_ROLE_ID,
                self.LT1_RANKED_ROLE_ID,
                self.HT2_RANKED_ROLE_ID,
                self.MT2_RANKED_ROLE_ID,
                self.LT2_RANKED_ROLE_ID,
                self.T3_RANKED_ROLE_ID,
                self.T4_RANKED_ROLE_ID,
                self.T5_RANKED_ROLE_ID,
                self.T6_RANKED_ROLE_ID,
                self.T7_RANKED_ROLE_ID,
                self.T8_RANKED_ROLE_ID,
            ]
            return list({r for r in roles if r > 0})

        def get_role_id_for_rank(self, rank_name: str) -> int | None:
            return self.get_freedom_role_id_for_rank(rank_name)

        def get_all_rank_role_ids(self) -> list[int]:
            roles = [
                self.R_ID,
                *self.get_all_freedom_rank_role_ids(),
                *self.get_all_ranked_role_ids(),
            ]
            return list({r for r in roles if r > 0})

else:

    class Settings:
        """Fallback lightweight settings loader reading environment variables and .env file."""

        def __init__(self):
            self._load_env_file()
            self.DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
            self.OWNER_ID = int(os.environ.get("OWNER_ID", "0") or "0")
            self.CATEGORY_ID = int(os.environ.get("CATEGORY_ID", "0") or "0")
            self.CHON_ID = int(os.environ.get("CHON_ID", "0") or "0")
            self.BAITAP_ID = int(os.environ.get("BAITAP_ID", "0") or "0")
            self.RANKED_CHANNEL_ID = int(
                os.environ.get("RANKED_CHANNEL_ID", "0") or "0"
            )
            self.UP_RANK = int(os.environ.get("UP_RANK", "0") or "0")
            self.CF_ID = int(os.environ.get("CF_ID", "0") or "0")
            self.SUBMIT_ID = int(os.environ.get("SUBMIT_ID", "0") or "0")
            self.WINNER_CHANNEL_ID = int(
                os.environ.get("WINNER_CHANNEL_ID", "0") or "0"
            )
            self.DOC_INTAKE_CHANNEL_ID = int(
                os.environ.get("DOC_INTAKE_CHANNEL_ID", "1535278288828633138")
                or "1535278288828633138"
            )
            self.DOC_CATEGORY_ID = int(
                os.environ.get("DOC_CATEGORY_ID", "1534147951797080174")
                or "1534147951797080174"
            )
            self.DOC_SEARCH_CHANNEL_ID = int(
                os.environ.get("DOC_SEARCH_CHANNEL_ID", "1553678782101979186")
                or "1553678782101979186"
            )
            self.DUEL_LOG_CHANNEL_ID = int(
                os.environ.get("DUEL_LOG_CHANNEL_ID", "1536199276273860638")
                or "1536199276273860638"
            )
            self.PROBLEM_ARCHIVE_CHANNEL_ID = int(
                os.environ.get("PROBLEM_ARCHIVE_CHANNEL_ID", "1548627763467128912")
                or "1548627763467128912"
            )
            # Hyper Generator Channels & Roles
            self.GENERATE_CHANNEL_ID = int(
                os.environ.get("GENERATE_CHANNEL_ID", "1550896415046377615") or "1550896415046377615"
            )
            self.INFO_CHANNEL_ID = int(
                os.environ.get("INFO_CHANNEL_ID", "1550896576636129320") or "1550896576636129320"
            )
            self.DATABASE_ARCHIVE_CHANNEL_ID = int(
                os.environ.get("DATABASE_ARCHIVE_CHANNEL_ID", "1548627763467128912") or "1548627763467128912"
            )
            self.CHUNK_ARCHIVE_CHANNEL_ID = int(
                os.environ.get("CHUNK_ARCHIVE_CHANNEL_ID", "0") or "0"
            )
            self.ARCHIVE_CHUNK_MB = int(
                os.environ.get("ARCHIVE_CHUNK_MB", "25") or "25"
            )
            self.ROLE_HYPER_ELITE_ID = int(
                os.environ.get("ROLE_HYPER_ELITE_ID", "1550901268392972299") or "1550901268392972299"
            )
            self.ROLE_HYPER_ULTRA_ID = int(
                os.environ.get("ROLE_HYPER_ULTRA_ID", "1550901272943657061") or "1550901272943657061"
            )
            self.ROLE_HYPER_PRO_ID = int(
                os.environ.get("ROLE_HYPER_PRO_ID", "1550901276689039431") or "1550901276689039431"
            )
            self.ROLE_HYPER_FREE_ID = int(
                os.environ.get("ROLE_HYPER_FREE_ID", "1550901280656859246") or "1550901280656859246"
            )
            self.ROLE_DIVIDER_ID = int(
                os.environ.get("ROLE_DIVIDER_ID", "1550901263154020504") or "1550901263154020504"
            )
            hidden_cats_env = os.environ.get(
                "RANKED_HIDDEN_CATEGORY_IDS",
                "1534147161091211414,1534147951797080174,1534148003701719070",
            )
            self.RANKED_HIDDEN_CATEGORY_IDS = [
                int(c.strip()) for c in hidden_cats_env.split(",") if c.strip().isdigit()
            ]
            self.GIAM_KHAO_ROLE_ID = int(
                os.environ.get("GIAM_KHAO_ROLE_ID", "0") or "0"
            )

            self.LOGO_ID = os.environ.get(
                "LOGO_ID", "https://assets.codeforces.com/favicon-96x96.png"
            )

            # Role Thành viên mặc định cho tất cả mọi người (🌱 Học sinh)
            self.MEMBER_ROLE_ID = int(os.environ.get("MEMBER_ROLE_ID", "0") or "0")

            # Retired
            self.R_ID = int(os.environ.get("R_ID", "0") or "0")

            # Freedom Roles
            self.HT1_FREEDOM_ROLE_ID = int(
                os.environ.get("HT1_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.MT1_FREEDOM_ROLE_ID = int(
                os.environ.get("MT1_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.LT1_FREEDOM_ROLE_ID = int(
                os.environ.get("LT1_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.HT2_FREEDOM_ROLE_ID = int(
                os.environ.get("HT2_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.MT2_FREEDOM_ROLE_ID = int(
                os.environ.get("MT2_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.LT2_FREEDOM_ROLE_ID = int(
                os.environ.get("LT2_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T3_FREEDOM_ROLE_ID = int(
                os.environ.get("T3_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T4_FREEDOM_ROLE_ID = int(
                os.environ.get("T4_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T5_FREEDOM_ROLE_ID = int(
                os.environ.get("T5_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T6_FREEDOM_ROLE_ID = int(
                os.environ.get("T6_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T7_FREEDOM_ROLE_ID = int(
                os.environ.get("T7_FREEDOM_ROLE_ID", "0") or "0"
            )
            self.T8_FREEDOM_ROLE_ID = int(
                os.environ.get("T8_FREEDOM_ROLE_ID", "0") or "0"
            )

            # Ranked Roles
            self.HT1_RANKED_ROLE_ID = int(
                os.environ.get("HT1_RANKED_ROLE_ID", "0") or "0"
            )
            self.MT1_RANKED_ROLE_ID = int(
                os.environ.get("MT1_RANKED_ROLE_ID", "0") or "0"
            )
            self.LT1_RANKED_ROLE_ID = int(
                os.environ.get("LT1_RANKED_ROLE_ID", "0") or "0"
            )
            self.HT2_RANKED_ROLE_ID = int(
                os.environ.get("HT2_RANKED_ROLE_ID", "0") or "0"
            )
            self.MT2_RANKED_ROLE_ID = int(
                os.environ.get("MT2_RANKED_ROLE_ID", "0") or "0"
            )
            self.LT2_RANKED_ROLE_ID = int(
                os.environ.get("LT2_RANKED_ROLE_ID", "0") or "0"
            )
            self.T3_RANKED_ROLE_ID = int(
                os.environ.get("T3_RANKED_ROLE_ID", "0") or "0"
            )
            self.T4_RANKED_ROLE_ID = int(
                os.environ.get("T4_RANKED_ROLE_ID", "0") or "0"
            )
            self.T5_RANKED_ROLE_ID = int(
                os.environ.get("T5_RANKED_ROLE_ID", "0") or "0"
            )
            self.T6_RANKED_ROLE_ID = int(
                os.environ.get("T6_RANKED_ROLE_ID", "0") or "0"
            )
            self.T7_RANKED_ROLE_ID = int(
                os.environ.get("T7_RANKED_ROLE_ID", "0") or "0"
            )
            self.T8_RANKED_ROLE_ID = int(
                os.environ.get("T8_RANKED_ROLE_ID", "0") or "0"
            )

            # Legacy Roles
            self.HT1_ROLE_ID = (
                int(os.environ.get("HT1_ROLE_ID", "0") or "0")
                or self.HT1_RANKED_ROLE_ID
                or self.HT1_FREEDOM_ROLE_ID
            )
            self.MT1_ROLE_ID = (
                int(os.environ.get("MT1_ROLE_ID", "0") or "0")
                or self.MT1_RANKED_ROLE_ID
                or self.MT1_FREEDOM_ROLE_ID
            )
            self.LT1_ROLE_ID = (
                int(os.environ.get("LT1_ROLE_ID", "0") or "0")
                or self.LT1_RANKED_ROLE_ID
                or self.LT1_FREEDOM_ROLE_ID
            )
            self.HT2_ROLE_ID = (
                int(os.environ.get("HT2_ROLE_ID", "0") or "0")
                or self.HT2_RANKED_ROLE_ID
                or self.HT2_FREEDOM_ROLE_ID
            )
            self.MT2_ROLE_ID = (
                int(os.environ.get("MT2_ROLE_ID", "0") or "0")
                or self.MT2_RANKED_ROLE_ID
                or self.MT2_FREEDOM_ROLE_ID
            )
            self.LT2_ROLE_ID = (
                int(os.environ.get("LT2_ROLE_ID", "0") or "0")
                or self.LT2_RANKED_ROLE_ID
                or self.LT2_FREEDOM_ROLE_ID
            )
            self.T3_ROLE_ID = (
                int(os.environ.get("T3_ROLE_ID", "0") or "0")
                or self.T3_RANKED_ROLE_ID
                or self.T3_FREEDOM_ROLE_ID
            )
            self.T4_ROLE_ID = (
                int(os.environ.get("T4_ROLE_ID", "0") or "0")
                or self.T4_RANKED_ROLE_ID
                or self.T4_FREEDOM_ROLE_ID
            )
            self.T5_ROLE_ID = (
                int(os.environ.get("T5_ROLE_ID", "0") or "0")
                or self.T5_RANKED_ROLE_ID
                or self.T5_FREEDOM_ROLE_ID
            )
            self.T6_ROLE_ID = (
                int(os.environ.get("T6_ROLE_ID", "0") or "0")
                or self.T6_RANKED_ROLE_ID
                or self.T6_FREEDOM_ROLE_ID
            )
            self.T7_ROLE_ID = (
                int(os.environ.get("T7_ROLE_ID", "0") or "0")
                or self.T7_RANKED_ROLE_ID
                or self.T7_FREEDOM_ROLE_ID
            )
            self.T8_ROLE_ID = (
                int(os.environ.get("T8_ROLE_ID", "0") or "0")
                or self.T8_RANKED_ROLE_ID
                or self.T8_FREEDOM_ROLE_ID
            )

            db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///bot.db")
            if db_url.startswith("sqlite:///"):
                db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            self.DATABASE_URL = db_url

            self.CF_API_KEY = os.environ.get("CF_API_KEY")
            self.CF_API_SECRET = os.environ.get("CF_API_SECRET")
            self.CF_SYNC_INTERVAL_SECONDS = int(
                os.environ.get("CF_SYNC_INTERVAL_SECONDS", "45") or "45"
            )

            self.JUDGE_TIMEOUT = int(os.environ.get("JUDGE_TIMEOUT", "5") or "5")
            self.JUDGE_MEMORY_LIMIT = int(
                os.environ.get("JUDGE_MEMORY_LIMIT", "256") or "256"
            )
            self.JUDGE_CPU_LIMIT = float(
                os.environ.get("JUDGE_CPU_LIMIT", "2.0") or "2.0"
            )
            self.JUDGE_PIDS_LIMIT = int(
                os.environ.get("JUDGE_PIDS_LIMIT", "64") or "64"
            )
            self.DOCKER_SANDBOX_IMAGE = os.environ.get(
                "DOCKER_SANDBOX_IMAGE", "cp-sandbox:latest"
            )
            self.USE_DOCKER_SANDBOX = (
                os.environ.get("USE_DOCKER_SANDBOX", "true").lower() == "true"
            )

            self.MAX_CODE_LENGTH = int(
                os.environ.get("MAX_CODE_LENGTH", "65536") or "65536"
            )
            self.SUBMIT_COOLDOWN_SECONDS = int(
                os.environ.get("SUBMIT_COOLDOWN_SECONDS", "15") or "15"
            )
            self.AI_SUSPICION_THRESHOLD = int(
                os.environ.get("AI_SUSPICION_THRESHOLD", "65") or "65"
            )
            self.AI_MODEL = os.environ.get(
                "AI_MODEL", os.environ.get("OLLAMA_MODEL", "Qwen3-4B-Instruct-2507")
            )
            self.OLLAMA_BASE_URL = os.environ.get(
                "OLLAMA_BASE_URL", "http://localhost:11434"
            )
            self.OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", self.AI_MODEL)
            self.OLLAMA_TIMEOUT = int(
                os.environ.get("OLLAMA_TIMEOUT", "1800") or "1800"
            )
            self.OLLAMA_NUM_GPU = int(
                os.environ.get("OLLAMA_NUM_GPU", "0") or "0"
            )
            self.AI_CORE_CHANNEL_ID = int(
                os.environ.get("AI_CORE_CHANNEL_ID", "1544356764240183358")
                or "1544356764240183358"
            )
            self.AI_CHAT_CHANNEL_ID = int(
                os.environ.get("AI_CHAT_CHANNEL_ID", "0") or "0"
            )
            self.LINK_SCANNER_CHANNEL_ID = int(
                os.environ.get("LINK_SCANNER_CHANNEL_ID", "1546522680638054461")
                or "1546522680638054461"
            )
            self.VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "") or ""
            self.ANTI_RAID_ENABLED = os.environ.get("ANTI_RAID_ENABLED", "true").lower() in ("true", "1")
            self.ANTI_SPAM_ENABLED = os.environ.get("ANTI_SPAM_ENABLED", "true").lower() in ("true", "1")
            self.ANTI_NUKE_AUTO_RESTORE = os.environ.get("ANTI_NUKE_AUTO_RESTORE", "true").lower() in ("true", "1")
            self.BACKUP_AUTO_INTERVAL_HOURS = int(os.environ.get("BACKUP_AUTO_INTERVAL_HOURS", "6") or "6")
            self.JOIN_FLOOD_THRESHOLD = int(os.environ.get("JOIN_FLOOD_THRESHOLD", "5") or "5")
            self.MESSAGE_FLOOD_THRESHOLD = int(os.environ.get("MESSAGE_FLOOD_THRESHOLD", "5") or "5")
            self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

        def _load_env_file(self):
            if os.path.exists(".env"):
                with open(".env", "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip()
                            if not (v.startswith('"') and v.endswith('"')) and not (
                                v.startswith("'") and v.endswith("'")
                            ):
                                if "#" in v:
                                    v = v.split("#", 1)[0].strip()
                            else:
                                v = v[1:-1]
                            os.environ.setdefault(k, v)

        def get_freedom_role_id_for_rank(self, rank_name: str) -> int | None:
            """Trả về ID của Role Freedom tương ứng với Bậc Rank."""
            mapping: dict[str, int] = {
                "HT1": self.HT1_FREEDOM_ROLE_ID or self.HT1_ROLE_ID,
                "MT1": self.MT1_FREEDOM_ROLE_ID or self.MT1_ROLE_ID,
                "LT1": self.LT1_FREEDOM_ROLE_ID or self.LT1_ROLE_ID,
                "HT2": self.HT2_FREEDOM_ROLE_ID or self.HT2_ROLE_ID,
                "MT2": self.MT2_FREEDOM_ROLE_ID or self.MT2_ROLE_ID,
                "LT2": self.LT2_FREEDOM_ROLE_ID or self.LT2_ROLE_ID,
                "T3": self.T3_FREEDOM_ROLE_ID or self.T3_ROLE_ID,
                "T4": self.T4_FREEDOM_ROLE_ID or self.T4_ROLE_ID,
                "T5": self.T5_FREEDOM_ROLE_ID or self.T5_ROLE_ID,
                "T6": self.T6_FREEDOM_ROLE_ID or self.T6_ROLE_ID,
                "T7": self.T7_FREEDOM_ROLE_ID or self.T7_ROLE_ID,
                "T8": self.T8_FREEDOM_ROLE_ID or self.T8_ROLE_ID,
            }
            role_id = mapping.get(rank_name.upper())
            return role_id if role_id and role_id > 0 else None

        def get_all_freedom_rank_role_ids(self) -> list[int]:
            """Trả về danh sách ID tất cả các Role Freedom."""
            roles = [
                self.HT1_FREEDOM_ROLE_ID,
                self.MT1_FREEDOM_ROLE_ID,
                self.LT1_FREEDOM_ROLE_ID,
                self.HT2_FREEDOM_ROLE_ID,
                self.MT2_FREEDOM_ROLE_ID,
                self.LT2_FREEDOM_ROLE_ID,
                self.T3_FREEDOM_ROLE_ID,
                self.T4_FREEDOM_ROLE_ID,
                self.T5_FREEDOM_ROLE_ID,
                self.T6_FREEDOM_ROLE_ID,
                self.T7_FREEDOM_ROLE_ID,
                self.T8_FREEDOM_ROLE_ID,
            ]
            return list({r for r in roles if r > 0})

        def get_ranked_role_id_for_rank(self, rank_name: str) -> int | None:
            """Trả về ID của Role Ranked 1:1 tương ứng với Bậc Rank."""
            mapping: dict[str, int] = {
                "HT1": self.HT1_RANKED_ROLE_ID,
                "MT1": self.MT1_RANKED_ROLE_ID,
                "LT1": self.LT1_RANKED_ROLE_ID,
                "HT2": self.HT2_RANKED_ROLE_ID,
                "MT2": self.MT2_RANKED_ROLE_ID,
                "LT2": self.LT2_RANKED_ROLE_ID,
                "T3": self.T3_RANKED_ROLE_ID,
                "T4": self.T4_RANKED_ROLE_ID,
                "T5": self.T5_RANKED_ROLE_ID,
                "T6": self.T6_RANKED_ROLE_ID,
                "T7": self.T7_RANKED_ROLE_ID,
                "T8": self.T8_RANKED_ROLE_ID,
            }
            role_id = mapping.get(rank_name.upper())
            return role_id if role_id and role_id > 0 else None

        def get_all_ranked_role_ids(self) -> list[int]:
            """Trả về danh sách ID tất cả các Role Ranked."""
            roles = [
                self.HT1_RANKED_ROLE_ID,
                self.MT1_RANKED_ROLE_ID,
                self.LT1_RANKED_ROLE_ID,
                self.HT2_RANKED_ROLE_ID,
                self.MT2_RANKED_ROLE_ID,
                self.LT2_RANKED_ROLE_ID,
                self.T3_RANKED_ROLE_ID,
                self.T4_RANKED_ROLE_ID,
                self.T5_RANKED_ROLE_ID,
                self.T6_RANKED_ROLE_ID,
                self.T7_RANKED_ROLE_ID,
                self.T8_RANKED_ROLE_ID,
            ]
            return list({r for r in roles if r > 0})

        def get_role_id_for_rank(self, rank_name: str) -> int | None:
            return self.get_freedom_role_id_for_rank(rank_name)

        def get_all_rank_role_ids(self) -> list[int]:
            roles = [
                self.R_ID,
                *self.get_all_freedom_rank_role_ids(),
                *self.get_all_ranked_role_ids(),
            ]
            return list({r for r in roles if r > 0})


settings = Settings()

# ============================================================
# SINGLE SOURCE OF TRUTH: AI MODEL NAMES
# Mọi module trong project PHẢI import từ đây, KHÔNG hardcode.
# ============================================================
AI_MODEL_NAME: str = getattr(settings, "AI_MODEL", "qwen3.5:4b")
AI_BACKUP_MODEL_NAME: str = getattr(settings, "AI_BACKUP_MODEL", "qwen3.5:2b")
AI_VERIFIER_MODEL_NAME: str = getattr(settings, "AI_VERIFIER_MODEL", "gemma3:4b")


def _detect_local_ffmpeg() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = ("ffmpeg.exe", "ffmpeg")
    for directory in (os.path.join(base_dir, "ffmpeg"), base_dir):
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"
