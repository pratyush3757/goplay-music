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

error_message_lifetime = None
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
            self.bot.loop.create_task(state.cancel_task_and_disconnect())
            
    def cog_check(self, ctx: commands.Context):
        """Check before invoking any command from the cog"""
        logger.debug(f"Received command from {ctx.author} in {ctx.channel}: {ctx.message.content}")
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        
        state = self.voice_states.get(ctx.guild.id)
        
        # Check for any command used before join,play,playtop. Prevents unnecessary player initialization.
        if not ((state is not None) or (ctx.command.name in ['join', 'play', 'playtop'])):
            return False
        
        return True
    
    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)
        
    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Cog command errors handler"""
        # This prevents any commands with local handlers being handled here in on_command_error.
        if ctx.command.has_error_handler():
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
        elif isinstance(error, commands.CheckFailure):
            logger.debug(f"[Music Cog] Command error: Command used before playing songs. {str(error)}")
            await self.send_error_embed(ctx, 
                                        title = "Command Error", 
                                        description = f"Please use play, playtop or join commands before using this command.")
        else:
            logger.error(f"[Music Cog] Command error: {str(error)}", exc_info = True)
            self.error_count += 1
            additional_info = ""
            if self.error_count >= 3:
                additional_info = "\nщ（ﾟДﾟщ）(╯°□°）╯︵ ┻━┻\nPlease ping the maintainer to look into this."
            
            #logger.error(f"[Music Cog] Command error: {str(error)}", exc_info = True)
            await self.send_error_embed(ctx,
                                        title = "Command Error",
                                        description = f"There has been an error.{additional_info}")
    
    async def cleanup(self, ctx, guild):
        try:
            await ctx.voice_state.cancel_task_and_disconnect()
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
        
    async def ensure_voice(ctx: commands.Context):
        """Ensures that user is connected to a voice channel"""
        
        if not ctx.author.voice or not ctx.author.voice.channel:
            #await self.send_error_embed(ctx, f"Please join a voice channel!")
            return False
        
        return True
        
    @commands.command(name='join', aliases=['j'])
    @commands.check(ensure_voice)
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel"""
        
        # Check necessary to prevent multiple join invoke errors from play command
        voice_client = discord.utils.get(self.bot.voice_clients, guild = ctx.guild)
        if (not ctx.voice_state.voice) and voice_client:
            ctx.voice_state.voice = ctx.voice_client
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
            
        await ctx.voice_state.cancel_task_and_disconnect()
        del self.voice_states[ctx.guild.id]
        
    @commands.command(name='embeds')
    async def _toggle_np_embed(self, ctx: commands.Context, value: str = None):
        """Toggles nowplaying embeds or sets a given state"""
        
        if value == None:
            value = ctx.voice_state.toggle_embed()
        elif value in ['y', 'Y', 'T', 't', '1', 'on', 'ON', 'On']:
            value = ctx.voice_state.toggle_embed(True)
        elif value in ['n', 'N', 'F', 'f', '0', 'off', 'OFF', 'Off']:
            value = ctx.voice_state.toggle_embed(False)
        
        msg = "on" if value else "off"
        await self.send_info_embed(ctx, f"Now playing embeds have been turned {msg}.")
        
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
            
    @commands.command(name='skip', aliases=['next'])
    async def _skip(self, ctx: commands.Context):
        """Skips song"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
            
        await ctx.message.add_reaction('⏭')
        ctx.voice_state.skip_song()
        
    @commands.command(name='skipto', aliases=['st'])
    async def _skipto(self, ctx: commands.Context, index: int):
        """Skips song to given queue number"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
            
        try:
            logger.debug(f"Skipto: current nowplaying = {ctx.voice_state.nowplaying_index}")
            await ctx.voice_state.skip_to_song(index)
        except IndexError:
            return await self.send_error_embed(ctx, f"Please check the index.")
        except:
            raise commands.CommandError(f'Skipto command has encountered an error.')
        else:
            await ctx.message.add_reaction('⏭')
        
    @commands.command(name='previous', aliases = ['prev'])
    async def _previous(self, ctx: commands.Context):
        """Playes the previous song"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
        
        if not ctx.voice_state.previous_playable:
            return await self.send_error_embed(ctx, f"There is no song before the currently playing song.")
        
        try:
            await ctx.voice_state.previous_song()
        except IndexError:
            return await self.send_error_embed(ctx, f"There was an error playing previous song.")
        else:
            await ctx.message.add_reaction('⏭')
        
    @commands.command(name='queue', aliases=['q', 'playlist', 'list'])
    async def _queue(self, ctx: commands.Context, page: int = 0):
        """Show the player's queue. 
        Can specify page to view. 10 entries per page"""
        
        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")
        
        playlist_len = len(ctx.voice_state.playlist[:])
        items_per_page = 10
        pages = math.ceil(playlist_len/items_per_page)
        
        nowplaying_index = ctx.voice_state.nowplaying_index
        logger.debug(f"Request for playlist page: {page}")
        page = math.ceil(nowplaying_index/items_per_page) if page == 0 else page
        logger.debug(f"Sending playlist page: {page}")
        
        start = (page - 1) * items_per_page
        end = start + items_per_page
        
        queue = ''
        for i, song in enumerate(ctx.voice_state.playlist[start:end], start = start):
            if i == nowplaying_index - 1:
                queue += f"`{i+1}.` \N{Headphone} [{song.title}]({song.url})\n"
            else:
                queue += f"`{i+1}.` [{song.title}]({song.url})\n"
            
        embed = discord.Embed(description = f"**{playlist_len - nowplaying_index} upcoming tracks:**\n\n{queue}", 
                               color = discord.Color.blurple()).set_footer(text = f"Viewing page {page}/{pages}")
        await ctx.send(embed = embed, delete_after = info_message_lifetime)
    
    @commands.command(name='history', aliases=['hist'])
    async def _hist(self, ctx: commands.Context, *, page: int = 1):
        """Show the player's queue. 
        Can specify page to view. 10 entries per page"""
        
        if len(ctx.voice_state.songs_history) == 0:
            return await self.send_info_embed(ctx, f"The played queue is empty.")
            
        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs_history)/items_per_page)
        
        start = (page - 1) * items_per_page
        end = start + items_per_page
        
        queue = ''
        for i, song in enumerate(ctx.voice_state.songs_history[start:end], start = start):
            queue += f"`{i+1}.` [**{song.title}**]({song.url})\n"
            
        embed = discord.Embed(description = f"**{len(ctx.voice_state.songs_history)} tracks have been played:**\n\n{queue}", 
                               color = discord.Color.green()).set_footer(text = f"Viewing page {page}/{pages}")
        await ctx.send(embed = embed, delete_after = info_message_lifetime)
        
    @commands.command(name='previnfo', aliases=['pi'])
    async def _previnfo(self, ctx: commands.Context):
        """Show info on previous song"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
        if not ctx.voice_state.previous_playable:
            return await self.send_error_embed(ctx, f"There is no song before the currently playing song.")
        
        _embed = await ctx.voice_state.prev_info_embed()
        await ctx.send(embed = _embed, delete_after = info_message_lifetime)
    
    @commands.command(name='nowplaying', aliases=['np','now','current'])
    async def _nowplaying(self, ctx: commands.Context):
        """Show Now Playing"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
        
        await ctx.send(embed = ctx.voice_state.current_info_embed(), delete_after = info_message_lifetime)
        
    @commands.command(name='nextinfo', aliases=['ni'])
    async def _nextinfo(self, ctx: commands.Context):
        """Show info on next song"""
        
        if not ctx.voice_state.is_loaded:
            return await self.send_info_embed(ctx, f"Nothing is playing right now.")
        elif ctx.voice_state.upcoming_empty:
            return await self.send_info_embed(ctx, f"There are no upcoming songs.")
        
        _embed = await ctx.voice_state.next_info_embed()
        await ctx.send(embed = _embed, delete_after = info_message_lifetime)
        
    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue"""

        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")

        ctx.voice_state.shuffle_queue()
        await ctx.message.add_reaction('\N{Twisted Rightwards Arrows}')
    
    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: str = None):
        """Removes a song from the queue at a given index or from a user"""

        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")
        
        if index == None:
            return await self.send_error_embed(ctx, f"Please provide a song to remove.")
        elif index.isdigit():
            try:
                ctx.voice_state.remove_song(int(index))
            except IndexError:
                return await self.send_error_embed(ctx, f"Please check the index.")
            else:
                await ctx.message.add_reaction('\N{White Heavy Check Mark}')
        else:
            if len(ctx.message.mentions) == 0:
                return await self.send_error_embed(ctx, f"Please provide a song to remove.")
            else:
                requesters_to_remove = []
                for user_mentioned in ctx.message.mentions:
                    requesters_to_remove.append(user_mentioned.id)
                    
                try:
                    count = await ctx.voice_state.remove_requesters(requesters_to_remove)
                    await self.send_info_embed(ctx, f"Removed {count} songs from the playlist.")
                except:
                    #await self.send_error_embed(ctx, f"There was an error in removing the songs")
                    raise commands.CommandError()
                    #await self.send_info_embed(ctx, f"{people} were mentioned.")
    
    @commands.command(name='remdupes')
    async def _remove_dupes(self, ctx: commands.Context):
        """Removes duplicate songs from the queue"""

        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")
        
        try:
            count = await ctx.voice_state.remove_dupes()
            await self.send_info_embed(ctx, f"Removed {count} songs from the playlist.")
        except:
            raise commands.CommandError()
        
    @commands.command(name='remabs')
    async def _remove_absent(self, ctx: commands.Context):
        """Removes songs requested by absent users"""

        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")
        
        try:
            present_members = ctx.voice_state.voice.channel.voice_states.keys()
            count = await ctx.voice_state.remove_absent(present_members)
            await self.send_info_embed(ctx, f"Removed {count} songs from the playlist.")
        except:
            raise commands.CommandError()
    
    @commands.command(name='clear', aliases=['cq'])
    async def _clear_queue(self, ctx: commands.Context):
        """Clears the queue"""
        
        ctx.voice_state.clear_queue()
    
    @commands.command(name='move', aliases = ['mv'])
    async def _move(self, ctx: commands.Context, old_index: int, new_index: int):
        """Moves a song in queue to a given index"""

        if ctx.voice_state.playlist_empty:
            return await self.send_info_embed(ctx, f"The playlist is empty.")
            
        try:
            await ctx.voice_state.move_song(old_index, new_index)
        except IndexError:
            return await self.send_error_embed(ctx, f"Please check the index.")
        else:
            await ctx.message.add_reaction('\N{Up Down Arrow}')

    @commands.command(name='play', aliases=['p'])
    @commands.check(ensure_voice)
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
        
        await ctx.voice_state.push_entry(source, pushTopFlag = pushTopFlag)
        
    @commands.command(name='playtop', aliases=['pt'])
    @commands.check(ensure_voice)
    async def _playtop(self, ctx: commands.Context, *, search: str):
        """Adds a given song to top of the queue"""
        
        await self._play(ctx, search = search, pushTopFlag = True)
                
    @commands.command(name='restart')
    async def _restart(self, ctx: commands.Context):
        try:
            await ctx.voice_state.restart_player()
        except Exception as e:
            logger.error(e)
            await self.send_error_embed(ctx, f"There has been an error in restarting the player")
    
    @_play.error
    @_playtop.error
    @_join.error
    async def play_handler(self, ctx: commands.Context, error: commands.CommandError):
        """Error handler for play and playtop commands"""
        
        if isinstance(error, commands.MissingRequiredArgument):
            logger.debug(f"[Music Cog] Command error: {str(error)}")
            if error.param.name == 'search':
                await self.send_error_embed(ctx, f"Please provide the link or search term to play song from.")
        
        elif isinstance(error, commands.CheckFailure):
            logger.debug(f"[Music Cog] Command error: {str(error)}")
            await self.send_error_embed(ctx, f"Please join a voice channel!")
            
        else:
            logger.error(f"[Music Cog] Command error: {str(error)}", exc_info = True)
            await self.send_error_embed(ctx,
                                        title = "Command Error",
                                        description = f"There has been an error.\nPlease ping the maintainer to look into this.")
            
    
async def setup(bot):
    await bot.add_cog(Music(bot))
