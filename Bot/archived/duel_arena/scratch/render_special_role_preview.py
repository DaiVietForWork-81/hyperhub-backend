import asyncio
import os
import shutil
from services.profile_card import ProfileCardGenerator

async def main():
    path = await ProfileCardGenerator.generate_profile_card(
        user_id=777888999,
        display_name="HyperMaster",
        avatar_url=None,
        joined_at_str="15/01/2025",
        standing=1,
        overall_pts=3150.0,
        freedom_tier="HT1",
        freedom_rating=3200,
        ranked_tier="HT1",
        ranked_rating=3100,
        title="Redstone Mastermind",
        user_role="member",
        special_role="CLUTCHMASTER",
        ranked_streak=18,
        ranked_max_streak=25,
        win_rate=88.5,
        total_wins=142,
        total_losses=18,
        cf_handle="tourist",
        cf_rating=3800,
        cf_max_rating=3979,
        force_refresh=True,
    )
    artifact_path = r"C:\Users\Mk2012\.gemini\antigravity\brain\07c0ffdf-2152-4957-888b-b55a82c9002d\sample_profile_with_special_role.png"
    shutil.copy2(path, artifact_path)
    print(f"Generated and copied to: {artifact_path}")

if __name__ == "__main__":
    asyncio.run(main())
