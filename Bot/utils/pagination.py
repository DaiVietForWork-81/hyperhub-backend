from __future__ import annotations

import discord


class PaginatedView(discord.ui.View):
    def __init__(self, embed_list: list[discord.Embed], author_id: int, timeout: int = 180) -> None:
        super().__init__(timeout=timeout)
        self.embed_list = embed_list
        self.author_id = author_id
        self.current = 0
        self._build_buttons()

    def _build_buttons(self) -> None:
        self.clear_items()

        prev = discord.ui.Button(
            label="\u25C0",
            style=discord.ButtonStyle.primary,
            disabled=self.current == 0,
        )
        prev.callback = self._previous
        self.add_item(prev)

        page_num = discord.ui.Button(
            label=f"{self.current + 1}/{len(self.embed_list)}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        self.add_item(page_num)

        nxt = discord.ui.Button(
            label="\u25B6",
            style=discord.ButtonStyle.primary,
            disabled=self.current == len(self.embed_list) - 1,
        )
        nxt.callback = self._next
        self.add_item(nxt)

        close = discord.ui.Button(label="\u2715", style=discord.ButtonStyle.danger)
        close.callback = self._close
        self.add_item(close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Bạn không thể tương tác với menu này.", ephemeral=True
            )
            return False
        return True

    async def _previous(self, interaction: discord.Interaction) -> None:
        self.current -= 1
        self._build_buttons()
        await interaction.response.edit_message(embed=self.embed_list[self.current], view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        self.current += 1
        self._build_buttons()
        await interaction.response.edit_message(embed=self.embed_list[self.current], view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.message.delete()