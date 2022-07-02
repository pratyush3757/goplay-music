import discord
from discord.ext import commands

with open("txts/owner.txt","r") as f:
    BOT_OWNER = int(f.read())

class Basics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.command(name='ping')
    async def _ping(self, ctx: commands.Context):
        """Ping pong"""
        
        await ctx.send('pong')
        
    @commands.command(name='status')
    async def _status(self, ctx: commands.Context):
        """Show bot commands status"""
        
        with open("txts/status.txt","r") as f:
            f_status = f.read()
        embed = (discord.Embed(title = "Commands Status",
                               description = f"**How broken am I?**\n```{f_status}\n```",
                               color = discord.Color.gold())
                .add_field(name = "Help",value= f"Ping <@{BOT_OWNER}> to fix something"))
        await ctx.send(embed = embed)

async def setup(bot):
    await bot.add_cog(Basics(bot))
