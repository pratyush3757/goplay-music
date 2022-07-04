import asyncio
import discord
import math
import re
import logging

from discord.ext import commands
from .ytdl import YTDLError, YTDLExtractorFlat, YTDLExtractorNonFlat, YTDLMetadata
from .player import VoiceState

logger = logging.getLogger('discord.' + __name__)
logger.setLevel(logging.DEBUG)

error_message_lifetime = 30
info_message_lifetime = None

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}
        self.error_count = 0
        
        self.regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    def validate_url(self, string: str):
        return re.match(self.regex, string) is not None
    
    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
            
        return state
    
    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())
            
    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        
        return True
    
    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)
        
    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Cog command errors handler"""
        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return
        
        ignored = (commands.CommandNotFound, )
        
        if isinstance(error, ignored):
            return
        elif isinstance(error, commands.NoPrivateMessage):
            try:
                embed = discord.Embed(title = "Command Error",
                                      description = f"{ctx.command} cannot be used in DMs.", 
                                      color = discord.Color.red())
                await ctx.author.send(embed = embed, delete_after = error_message_lifetime)
            except discord.HTTPException:
                pass
        else:
            self.error_count += 1
            additional_info = ""
            if self.error_count >= 3:
                additional_info = "\nPlease ping the maintainer to look into this."
            
            logger.error(f"[Music Cog] Command error: {str(error)}", exc_info = True)
            await self.send_error_embed(ctx, f"There has been an error.{additional_info}")
    
    async def cleanup(self, ctx, guild):
        try:
            await ctx.voice_state.stop()
            await self.send_error_embed(ctx, title = f"Player Timeout",
                                        description = f"The player has timed out due to being idle.\nLeaving the voice channel.",
                                        lifetime = None)
        except AttributeError:
            pass

        try:
            del self.voice_states[guild.id]
        except KeyError:
            pass
        
    async def send_info_embed(self, ctx: commands.Context, 
                              description: str, title: str = None, 
                              lifetime: float = info_message_lifetime):
        _embed = discord.Embed(title = title,
                               description = description, 
                               color =  discord.Color.gold())
        await ctx.send(embed = _embed, delete_after = lifetime)
    
    async def send_error_embed(self, ctx: commands.Context,
                               description: str, title: str = "Command Error",
                               lifetime: float = error_message_lifetime):
        _embed = discord.Embed(title = title,
                               description = description, 
                               color =  discord.Color.red())
        await ctx.send(embed = _embed, delete_after = lifetime)
        
    @commands.command(name='join', aliases=['j'])
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel"""
        
        # Check necessary to prevent multiple join invoke errors from play command
        voice_client = discord.utils.get(self.bot.voice_clients, guild = ctx.guild)
        if (not ctx.voice_state.voice) and voice_client:
            ctx.voice_state.voice = ctx.voice_client.channel
            return
        
        voice_channel = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(voice_channel)
        else:
            ctx.voice_state.voice = await voice_channel.connect()
            
    @commands.command(name='disconnect', aliases=['leave','stop'])
    async def _disconnect(self, ctx: commands.Context):
        """Stops and Leaves voice channel"""
        
        if not ctx.voice_state.voice:
            return await self.send_error_embed(ctx, f"Bot not connected to any voice channel.")
            
        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        
    #@commands.command(name='volume', aliases=['vol'])
    #async def _volume(self, ctx: commands.Context, *, volume: int):
        #"""Changes the volume"""
        
        #if not ctx.voice_state.is_loaded:
            #return await ctx.send("Nothing is playing right now.")
        
        #volume = (volume / 100) % 1
        #ctx.voice_state.volume = volume
        #await ctx.send(f"Changed volume to {volume*100}")
        
    @commands.command(name='pause')
    async def _pause(self, ctx: commands.Context):
        """Pauses music"""
        
        if ctx.voice_state.is_loaded and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')
        
    @commands.command(name='resume', aliases=['res'])
    async def _resume(self, ctx: commands.Context):
        """Resumes playing music"""
        
        if ctx.voice_state.is_loaded and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')
            
    @commands.command(name='clear', aliases=['cq'])
    async def _clear_queue(self, ctx: commands.Context):
        """Clears the queue"""
        
        ctx.voice_state.songs.clear()
        
    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Skips song"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
            
        await ctx.message.add_reaction('⏭')
        ctx.voice_state.skip()
        
    @commands.command(name='queue', aliases=['q', 'playlist', 'list'])
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Show the player's queue. 
        Can specify page to view. 10 entries per page"""
        
        if len(ctx.voice_state.songs) == 0:
            return await self.send_info_embed(ctx, f"The queue is empty.")
            
        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs)/items_per_page)
        
        start = (page - 1) * items_per_page
        end = start + items_per_page
        
        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start = start):
            queue += f"`{i+1}.` [**{song.title}**]({song.url})\n"
            
        embed = discord.Embed(description = f"**{len(ctx.voice_state.songs)} tracks:**\n\n{queue}", 
                               color = discord.Color.blurple()).set_footer(text = f"Viewing page {page}/{pages}")
        await ctx.send(embed = embed, delete_after = info_message_lifetime)
    
    @commands.command(name='nowplaying', aliases=['np','now','current'])
    async def _nowplaying(self, ctx: commands.Context):
        """Show Now Playing"""
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
        
        await ctx.send(embed=ctx.voice_state.current.create_embed(), delete_after = info_message_lifetime)
        
    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue"""

        if len(ctx.voice_state.songs) == 0:
            return await self.send_info_embed(ctx, f"The queue is empty.")

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('\N{Twisted Rightwards Arrows}')
    
    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index"""

        if len(ctx.voice_state.songs) == 0:
            return await self.send_info_embed(ctx, f"The queue is empty.")

        try:
            ctx.voice_state.songs.remove(index - 1)
        except IndexError:
            return await self.send_error_embed(ctx, f"Please check the index.")
        else:
            await ctx.message.add_reaction('\N{White Heavy Check Mark}')
            
    @commands.command(name='move', aliases = ['mv'])
    async def _move(self, ctx: commands.Context, old_index: int, new_index: int):
        """Moves a song in queue to a given index"""

        if len(ctx.voice_state.songs) == 0:
            return await self.send_info_embed(ctx, f"The queue is empty.")
            
        try:
            ctx.voice_state.songs.move(old_index - 1, new_index -1)
        except IndexError:
            return await self.send_error_embed(ctx, f"Please check the index.")
        else:
            await ctx.message.add_reaction('\N{Up Down Arrow}')

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, search: str, pushTopFlag: bool = False):
        """Plays music from given url or search string"""

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)
            
        source = None
        async with ctx.typing():
            try:
                if self.validate_url(search):
                    source = await YTDLExtractorFlat.fetch_metadata(ctx, search, loop = self.bot.loop)
                else:
                    source = await YTDLExtractorNonFlat.fetch_metadata(ctx, search, loop = self.bot.loop)
                        
            except YTDLError as e:
                logger.error(e, exc_info = True)
                return await self.send_error_embed(ctx, title = "YoutubeDl Error",
                                                   description = f"An error occured while processing the request: {str(e)}")
            else:
                if isinstance(source, YTDLMetadata):
                    await self.send_info_embed(ctx, f"Enqueued {str(source)}")
                elif isinstance(source, list):
                    await self.send_info_embed(ctx, f"Enqueued {len(source)} songs.")
                    
        await ctx.voice_state.pushEntry(source, ctx, loop = self.bot.loop, pushTopFlag = pushTopFlag)
        
    @commands.command(name='playtop', aliases=['pt'])
    async def _playtop(self, ctx: commands.Context, *, search: str):
        """Adds a given song to top of the queue"""
        
        await self._play(ctx, search = search, pushTopFlag = True)
                
    @_play.error
    @_playtop.error
    async def play_handler(self, ctx: commands.Context, error: commands.CommandError):
        """Error handler for play and playtop commands"""
        
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'search':
                await self.send_error_embed(ctx, f"Please provide the link or search term to play song from.")
    
    @_join.before_invoke
    @_play.before_invoke
    @_playtop.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        """Ensures that user is connected to a voice channel"""
        
        if not ctx.author.voice or not ctx.author.voice.channel:
            await self.send_error_embed(ctx, f"Please join a voice channel!")
            return False

async def setup(bot):
    await bot.add_cog(Music(bot))
