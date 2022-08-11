import asyncio
import time
import itertools
import random
import queue
import logging

from async_timeout import timeout
from discord.ext import commands, tasks
from .ytdl import *

logger = logging.getLogger('discord.' + __name__)
logger.setLevel(logging.DEBUG)

error_message_lifetime = None
info_message_lifetime = None

class SongQueue(asyncio.Queue):
    """An async queue for songs"""
    def __getitem__(self, item):
        try:
            if isinstance(item, slice):
                return list(itertools.islice(self._queue, item.start, item.stop, item.step))
            else:
                return self._queue[item]
        except IndexError:
            raise IndexError()
        
    def __iter__(self):
        return self._queue.__iter__()
    
    def __len__(self):
        return self.qsize()
    
    def clear(self):
        self._queue.clear()
    
    def shuffle(self):
        random.shuffle(self._queue)
        
    def remove(self, index: int):
        try:
            del self._queue[index]
        except IndexError:
            raise IndexError()

    async def appendleft(self, x):
        if self.qsize() == 0:   # Check added to signal the async queue.get() that something has been added
                                # If we simply appendleft to an empty queue,
                                # queue.get() doesn't get know that the queue now has entries
            await self.put(x)
        else:
            self._queue.appendleft(x)
            
    def move(self, old_idx: int, new_idx: int):
        try:
            item = self._queue[old_idx]
            self.remove(old_idx)
        except IndexError:
            raise IndexError()
        else:
            if new_idx < 0:
                new_idx = 0
            self._queue.insert(new_idx, item)

class VoiceState:
    """Class defining a music player that uses a queue"""
    #__slots__ = ('bot', '_ctx', '_guild', '_channel', '_cog', 'current', 'voice', 'next', 'songs', 'songs_history', 'queuebuffer', '_bufferflag', '_loop', '_volume', '_send_embed', 'audio_player')
    
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog
        
        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self.songs_history = SongQueue()
        self.queuebuffer = queue.Queue()
        
        self._bufferflag = False
        self._loop = False
        self._volume = 0.5
        self._send_embed = False
        
        #self.audio_player = ctx.bot.loop.create_task(self.audio_player_task())
        self.audio_player = self.audio_player_task.start()
        
    def __del__(self):
        self.audio_player_task.cancel()
        
    @property
    def bufferflag(self):
        return self._bufferflag

    @bufferflag.setter
    def bufferflag(self, value: bool):
        self._bufferflag = value
        
    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume
    
    @volume.setter
    def volume(self, value: float):
        self._volume = value
        self.current.volume = self._volume
        
    @property
    def send_embed(self):
        return self._send_embed
    
    @send_embed.setter
    def send_embed(self, value: bool):
        self._send_embed = value
        
    @property
    def is_loaded(self):
        return self.voice and self.current
    
    @property
    def queue_empty(self):
        return len(self.songs) == 0
    
    @property
    def previous_playable(self):
        return len(self.songs_history) >= 2
    
    async def push_queuebuffer(self, pushTopFlag: bool = False):
        start = time.time()
        while self.queuebuffer.qsize() > 0:
            item = self.queuebuffer.get()
            if pushTopFlag:
                await self.songs.appendleft(item)
            else:
                await self.songs.put(item)
            #if isinstance(item, YTDLMetadata):      # Link's already been processed
                #await self.songs.put(item)
            #elif isinstance(item, BasicMetadata):   # A basic metadata obj is in the buffer from a playlist
                #await self.songs.put(item)
                
        #self._bufferflag = False
        end = time.time()
        logger.debug(f"Took {end-start} seconds to push all songs into the queue")

    async def push_entry(self, source, pushTopFlag: bool = False):
        if isinstance(source, YTDLMetadata):
            if pushTopFlag:
                await self.songs.appendleft(source)
            else:       # Blocking new entries from entering the queue while pushing of buffer by 
                        # Bufferflag method disabled considering speed of pushing 
                        # the complete buffer to songqueue is fast enough.
                await self.songs.put(source)
            #elif not self.bufferflag:
                #await self.songs.put(source)
            #else:
                #self.queuebuffer.put(source)
        elif isinstance(source, list):
            if pushTopFlag:
                source = reversed(source)
            #self.bufferflag = True
            for i in source:
                self.queuebuffer.put(i)
            await self.push_queuebuffer(pushTopFlag)

    @tasks.loop()
    async def audio_player_task(self):
        #while not self.bot.is_closed():
        if not self.bot.is_closed():
            logger.info("Audio Player Initiated")
            self.next.clear()
            
            if True:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                newsource = None
                try:
                    logger.debug("Waiting to play")
                    async with timeout(180): # 3 minutes
                        logger.debug("Getting the song")
                        self.current = await self.songs.get()
                        logger.debug("Got the song")
                        newsource = await YTDLSource.create_source(self.current.ctx, self.current.url, loop = self.bot.loop)
                        self.current = YTDLMetadata(newsource.ctx, newsource.data)
                        logger.debug("Got the audiosource")
                        
                except asyncio.TimeoutError as e:
                    logger.info("Timed out while waiting for song")
                    #raise VoiceError(str(e))
                    return self.destroy(self._ctx, self._guild)
                
                logger.debug("Playing song")
                self.voice.play(newsource.audio_source, after = lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
                if self._send_embed == True:
                    await self.current.channel.send(embed=self.current.create_embed(), delete_after = info_message_lifetime)
                
                await self.songs_history.put(self.current)
                await self.next.wait()
                logger.debug("Done playing the song")
                self.voice.stop()
                self.current = None
                newsource = None
    
    @audio_player_task.before_loop
    async def before_audio_player(self):
        await self.bot.wait_until_ready()
    
    def skip_song(self):
        if self.is_loaded:
            self.voice.stop() 
            # Causes the current stream to stop and the 
            # "after=" parameter in play function to be called
            
    async def skip_to_song(self, index: int):
        if len(self.songs) >= index:
            try:
                for i in range(index - 1):
                    entry = self.songs[0]
                    self.songs.remove(0)
                    await self.songs_history.put(entry)
                    logger.debug(f"pushed {str(entry)} to history")
            except Exception as e:
                logger.error(e)
                raise
            else:
                self.skip_song()
        else:
            raise IndexError()
        
    async def previous_song(self):
        if self.previous_playable:
            try:
                nowplaying_song = self.songs_history[-1]
                prev_song = self.songs_history[-2]
                self.songs_history.remove(-1) # Removing last 2 songs by using the last index for both
                self.songs_history.remove(-1)
            except IndexError:
                raise IndexError()
            else:
                # Had to push both entries as a list instead of individually,
                # it was having some weird async problem with the queue after using skipto command
                # where after skipto, using previous caused nowplaying to repeat and the previous to be dropped from the queue.
                # Maybe due to single entry push using queue.put() or some async desynchronization.
                await self.push_entry([prev_song, nowplaying_song], pushTopFlag = True)
                self.skip_song()
        else:
            raise IndexError()
    
    async def prev_info_embed(self):
        if self.previous_playable:
            song = self.songs_history[-2]
            if isinstance(song, YTDLMetadata):
                return song.create_embed()
            else:
                newsource = await YTDLSource.create_source(song.ctx, song.url, loop = self.bot.loop)
                song = YTDLMetadata(newsource.ctx, newsource.data)
                return song.create_embed()
    
    def current_info_embed(self):
        return self.current.create_embed()
    
    async def next_info_embed(self):
        if not self.queue_empty:
            song = self.songs[0]
            if isinstance(song, YTDLMetadata):
                return song.create_embed()
            else:
                newsource = await YTDLSource.create_source(song.ctx, song.url, loop = self.bot.loop)
                song = YTDLMetadata(newsource.ctx, newsource.data)
                return song.create_embed()
    
    def shuffle_queue(self):
        self.songs.shuffle()
        
    def remove_song(self, index: int):
        return self.songs.remove(index - 1)
        
    async def remove_requesters(self, requesters_to_remove: list):
        try:
            # This code block is equivalent to, but easier to understand than
            # modified_playlist = [v for v in self.songs[:] if v.requester.id not in requesters_to_remove]
            start = time.time()
            modified_playlist = []
            count = 0
            for song in self.songs[:]:
                if song.requester.id not in requesters_to_remove:
                    modified_playlist.append(song)
                else:
                    count +=1
            self.clear_queue()
            await self.push_entry(modified_playlist)
            end = time.time()
            logger.debug(f"Took [{end-start}] seconds to remove requesters")
            return count
        except Exception as e:
            logger.error(e)
            raise
        
    async def remove_dupes(self):
        try:
            start = time.time()
            modified_playlist = []
            count = 0
            url_set = {}
            for song in self.songs[:]:
                if song.url not in url_set:
                    modified_playlist.append(song)
                    url_set.add(song.url)
                else:
                    count +=1
            self.clear_queue()
            await self.push_entry(modified_playlist)
            end = time.time()
            logger.debug(f"Took [{end-start}] seconds to remove dupes")
            return count
        except Exception as e:
            logger.error(e)
            raise
    
    async def remove_absent(self, present_members: list):
        try:
            # Block is equivalent to, but easier to understand than
            # modified_playlist = [v for v in self.songs[:] if v.requester.id in present_members]
            start = time.time()
            modified_playlist = []
            count = 0
            for song in self.songs[:]:
                if song.requester.id in present_members:
                    modified_playlist.append(song)
                else:
                    count +=1
            self.clear_queue()
            await self.push_entry(modified_playlist)
            end = time.time()
            logger.debug(f"Took [{end-start}] seconds to remove songs by absent users")
            return count
        except Exception as e:
            logger.error(e)
            raise
    
    def clear_queue(self):
        self.songs.clear()
        
    def move_song(self, old_idx: int, new_idx: int):
        return self.songs.move(old_idx - 1, new_idx - 1)
    
    def toggle_embed(self, value: bool = None):
        if value == None:
            self.send_embed = not self.send_embed
            return self.send_embed
        self.send_embed = value
        return value
            
    def destroy(self, ctx, guild):
        """Destroy and clean the player"""
        return self.bot.loop.create_task(self._cog.cleanup(ctx, guild))
    
    async def restart_player(self):
        self.audio_player_task.cancel()
        self.next.set()
        try:
            nowplaying_song = self.songs_history[-1]
            self.songs_history.remove(-1)
        except IndexError:
            raise IndexError()
        else:
            await self.push_entry([nowplaying_song], pushTopFlag = True)
        await asyncio.sleep(1)
        self.audio_player_task.start()
    
    
    async def stop(self):
        self.songs.clear()
        
        if self.voice:
            await self.voice.disconnect()
            self.voice = None
            self.current = None
