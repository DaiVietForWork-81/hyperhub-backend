"""Repository for managing Codeforces linked accounts and verification state."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import CFAccount, User


class CFAccountRepository:
    """Manages database operations for Codeforces accounts."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_discord_id(self, discord_id: int) -> CFAccount | None:
        stmt = select(CFAccount).where(CFAccount.discord_id == discord_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_handle(self, cf_handle: str) -> CFAccount | None:
        stmt = select(CFAccount).where(CFAccount.cf_handle.ilike(cf_handle))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def link_account(
        self,
        discord_id: int,
        cf_handle: str,
        verification_token: str = "",
        verified: bool = True,
    ) -> CFAccount:
        """Tạo hoặc cập nhật liên kết tài khoản Codeforces (mặc định verified=True)."""
        # Đảm bảo user đã tồn tại
        user_stmt = select(User).where(User.discord_id == discord_id)
        user = (await self.session.execute(user_stmt)).scalar_one_or_none()
        if not user:
            user = User(
                discord_id=discord_id,
                rating=0,
                rank="T8",
                created_at=datetime.datetime.now(datetime.timezone.utc),
                updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
            self.session.add(user)
            await self.session.flush()

        cf_account = await self.get_by_discord_id(discord_id)
        if cf_account:
            cf_account.cf_handle = cf_handle
            cf_account.verified = verified
            cf_account.verification_token = verification_token
            cf_account.linked_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            cf_account = CFAccount(
                discord_id=discord_id,
                cf_handle=cf_handle,
                verified=verified,
                verification_token=verification_token,
                linked_at=datetime.datetime.now(datetime.timezone.utc),
            )
            self.session.add(cf_account)

        user.codeforces_handle = cf_handle
        await self.session.commit()
        await self.session.refresh(cf_account)
        return cf_account

    async def set_verified(
        self, discord_id: int, verified: bool = True
    ) -> CFAccount | None:
        """Marks account as verified."""
        cf_account = await self.get_by_discord_id(discord_id)
        if cf_account:
            cf_account.verified = verified
            if verified:
                cf_account.verification_token = None
            await self.session.commit()
            await self.session.refresh(cf_account)
        return cf_account

    async def unlink_account(self, discord_id: int) -> bool:
        """Unlinks Codeforces account from user."""
        cf_account = await self.get_by_discord_id(discord_id)
        if not cf_account:
            return False

        # Clear handle from User table as well
        user_stmt = select(User).where(User.discord_id == discord_id)
        user = (await self.session.execute(user_stmt)).scalar_one_or_none()
        if user:
            user.codeforces_handle = None

        await self.session.delete(cf_account)
        await self.session.commit()
        return True

    async def get_all_verified_accounts(self) -> list[CFAccount]:
        """Retrieves all verified Codeforces accounts for background synchronizer."""
        stmt = select(CFAccount).where(CFAccount.verified == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_verified(self) -> list[CFAccount]:
        """Alias cho get_all_verified_accounts."""
        return await self.get_all_verified_accounts()

    async def update_last_submission_id(
        self, discord_id: int, submission_id: int
    ) -> None:
        """Updates the highest processed submission ID to prevent redundant processing."""
        cf_account = await self.get_by_discord_id(discord_id)
        if cf_account:
            if (
                not cf_account.last_synced_submission_id
                or submission_id > cf_account.last_synced_submission_id
            ):
                cf_account.last_synced_submission_id = submission_id
                await self.session.commit()
