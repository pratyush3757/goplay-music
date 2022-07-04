import asyncio

import discord
import logging
import logging.handlers
from discord.ext import commands

# Setting up Logger
logger = logging.getLogger('discord')
logger.setLevel(logging.ERROR)
logging.getLogger('discord.http').setLevel(logging.ERROR)

handler = logging.handlers.RotatingFileHandler(
    filename='logs/discord.log',
    encoding='utf-8',
    maxBytes=16 * 1024 * 1024,  # 16 MiB
    backupCount=3,  # Rotate through 3 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)


initialExtensions = ['cogs.music.music', 'cogs.basics']

with open("txts/token.txt","r") as f:
    token = f.read()

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix=commands.when_mentioned_or(";"), intents=intents)


@client.command(name="reload")
@commands.check_any(commands.is_owner(), commands.has_any_role("Helpers", "Moderators", "Admins"))
async def _reload(ctx: commands.Context, ext: str):
    """Reloads the specified module"""
    
    if ext in ["music", "Music"]:
        await client.reload_extension('cogs.music.music')
        await ctx.send("Reloaded the music module!")
    elif ext in initialExtensions:
        await client.reload_extension(ext)
        await ctx.send(f"Reloaded the {ext} module!")

@client.event
async def on_ready():
    await client.change_presence(activity=discord.Game('with fire'))

async def load_extensions():
    for extension in initialExtensions:
        await client.load_extension(extension)

async def main():
    async with client:
        await load_extensions()
        await client.start(token)

asyncio.run(main())
