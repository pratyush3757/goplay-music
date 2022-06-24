import asyncio
import discord
import math
import re

from discord.ext import commands
from .ytdl import YTDLError, YTDLExtractorFlat, YTDLExtractorNonFlat, YTDLMetadata
from .player import VoiceState


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}
        
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
            raise commands.NoPrivateMessage("This command can't be used in DMs.")
        
        return True
    
    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)
        
    #async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        ##await ctx.send('An error occurred: {}'.format(str(error)))
        #print("Error:", error)
    
    #async def cleanup(self, guild):
        #try:
            #await ctx.voice_state.stop()
        #except AttributeError:
            #pass

        #try:
            #del self.voice_states[guild.id]
        #except KeyError:
            #pass
        
    @commands.command(name='join', aliases=['j'])
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel"""
        
        voice_channel = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(voice_channel)
        else:
            ctx.voice_state.voice = await voice_channel.connect()
            
    @commands.command(name='disconnect', aliases=['leave','stop'])
    async def _disconnect(self, ctx: commands.Context):
        """Stops and Leaves voice channel"""
        
        if not ctx.voice_state.voice:
            return await ctx.send("Not connected to any voice channel.")
        
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
            await ctx.send("Paused music")
        
    @commands.command(name='resume', aliases=['res'])
    async def _resume(self, ctx: commands.Context):
        """Resumes playing music"""
        
        if ctx.voice_state.is_loaded and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')
            await ctx.send("Resumed music")
            
    @commands.command(name='clear', aliases=['cq'])
    async def _clear_queue(self, ctx: commands.Context):
        """Clears the queue"""
        
        ctx.voice_state.songs.clear()
        
    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Skips song"""
        
        if not ctx.voice_state.is_loaded:
            return await ctx.send("Nothing is playing right now.")
        
        await ctx.message.add_reaction('⏭')
        ctx.voice_state.skip()
        #await ctx.voice_state.play_next_non_async_event()
        
    @commands.command(name='queue', aliases=['q'])
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Show the player's queue. 
        Can specify page to view. 10 entries per page"""
        
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send("Queue Empty.")
        
        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs)/items_per_page)
        
        start = (page - 1) * items_per_page
        end = start + items_per_page
        
        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start = start):
            queue += f"`{i+1}.` [**{song.title}**]({song.url})\n"
            
        embed = (discord.Embed(description = f"**{len(ctx.voice_state.songs)} tracks:**\n\n{queue}", color = discord.Color.blurple()).set_footer(text = f"Viewing page {page}/{pages}"))
        await ctx.send(embed = embed)
    
    @commands.command(name='nowplaying', aliases=['np','now','current'])
    async def _nowplaying(self, ctx: commands.Context):
        """Show Now Playing"""
        await ctx.send(embed=ctx.voice_state.current.create_embed())
        
    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue"""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('\N{Twisted Rightwards Arrows}')
    
    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index"""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, search: str):
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
                await ctx.send(f"An error occured while processing the request: {str(e)}")
            else:
                if isinstance(source, YTDLMetadata):
                    await ctx.send(f"Enqueued {str(source)}")
                elif isinstance(source, list):
                    await ctx.send(f"Enqueued {len(source)} songs.")
        await ctx.voice_state.pushEntry(source, ctx, loop = self.bot.loop)
                
    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("Please join a voice channel!")
        
        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError("Bot already in a voice channel, please use join command")
            

async def setup(bot):
    await bot.add_cog(Music(bot))
