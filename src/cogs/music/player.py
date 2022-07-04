import asyncio
import time
import itertools
import random
import queue
import logging

from async_timeout import timeout
from discord.ext import commands
from .ytdl import *

logger = logging.getLogger('discord.' + __name__)
logger.setLevel(logging.INFO)

error_message_lifetime = 30
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
    __slots__ = ('bot', '_ctx', '_guild', '_channel', '_cog', 'current', 'voice', 'next', 'songs', 'queuebuffer', '_bufferflag', '_loop', '_volume', '_send_embed', 'audio_player')
    
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
        self.queuebuffer = queue.Queue()
        
        self._bufferflag = False
        self._loop = False
        self._volume = 0.5
        self._send_embed = False
        
        self.audio_player = ctx.bot.loop.create_task(self.audio_player_task())
        
    def __del__(self):
        self.audio_player.cancel()
        
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
    
    async def push_queuebuffer(self, ctx: commands.Context, loop: asyncio.BaseEventLoop = None, pushTopFlag: bool = False):
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

    async def pushEntry(self, source, ctx: commands.Context, loop: asyncio.BaseEventLoop = None, pushTopFlag: bool = False):
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
            await self.push_queuebuffer(ctx, loop, pushTopFlag)

    async def audio_player_task(self):
        while not self.bot.is_closed():
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
                
                logger.debug("Paying song")
                self.voice.play(newsource.audio_source, after = lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
                if self._send_embed == True:
                    await self.current.channel.send(embed=self.current.create_embed(), delete_after = info_message_lifetime)
                
                await self.next.wait()
                logger.debug("Done playing the song")
                self.voice.stop()
                self.current = None
                newsource = None
        
    def destroy(self, ctx, guild):
        """Destroy and clean the player"""
        return self.bot.loop.create_task(self._cog.cleanup(ctx, guild))

    def play_next_song(self, error = None):
        if error:
            raise VoiceError(str(error))
        
        self.next.set()
        
    def skip(self):
        if self.is_loaded:
            self.voice.stop() 
            # Causes the current stream to stop and the 
            # "after=" parameter in play function to be called
            
    async def stop(self):
        self.songs.clear()
        
        if self.voice:
            await self.voice.disconnect()
            self.voice = None
            self.current = None
