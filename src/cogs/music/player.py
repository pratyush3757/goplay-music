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
            
    def insert(self, idx: int, item):
        self._queue.insert(idx, item)

class Playlist:
    """Class rewriting songs queues, while merging upcoming and history queues behind an interface"""
    def __init__(self):
        self.upcoming = SongQueue()
        self.history = SongQueue()
        
    def __del__(self):
        self.clear_all_queues()
    
    @property
    def _playlist(self):
        return self.history[:] + self.upcoming[:]
    
    @property
    def nowplaying_index(self):
        """Return the position of nowplaying song in playlist as per users, (equals to when indexing starts at 1)"""
        return len(self.history)
        
    @property
    def upcoming_empty(self):
        return len(self.upcoming) == 0
    
    @property
    def history_empty(self):
        return len(self.history) == 0
    
    @property
    def playlist_empty(self):
        return len(self._playlist) == 0
    
    @property
    def previous_playable(self):
        return len(self.history) >= 2
    
    @property
    def prev_song(self):
        if self.previous_playable:
            return self.history[-2]
    
    @property
    def next_song(self):
        if not self.upcoming_empty:
            return self.upcoming[0]
    
    async def get(self):
        return await self.upcoming.get()
    
    async def put_history(self, item):
        await self.history.put(item)
    
    def __getitem__(self, item):
        try:
            if isinstance(item, slice):
                return list(itertools.islice(self._playlist, item.start, item.stop, item.step))
            else:
                return self._playlist[item]
        except IndexError:
            raise IndexError()
        
    async def push_entry(self, source, pushTopFlag: bool = False):
        if isinstance(source, YTDLMetadata):
            if pushTopFlag:
                await self.upcoming.appendleft(source)
            else:
                await self.upcoming.put(source)
        elif isinstance(source, list):
            start = time.perf_counter_ns()
            if pushTopFlag:
                source = reversed(source)
                for i in source:
                    await self.upcoming.appendleft(i)
            else:
                for i in source:
                    await self.upcoming.put(i)
            end = time.perf_counter_ns()
            logger.debug(f"Took {end-start} nanoseconds to push all songs into the queue")
    
    async def shift_queues_to(self, index: int):
        if 0 <= index <= len(self._playlist):
            try:
                # case index == self.nowplaying_index not needed as it won't shift anything
                if index < self.nowplaying_index:
                    # shift hist to upcoming
                    list_buffer = []
                    for _ in range(self.nowplaying_index - index):
                        entry = self.history[-1]
                        list_buffer.append(entry)
                        self.history.remove(-1)
                    list_buffer = list(reversed(list_buffer))
                    await self.push_entry(list_buffer, True)
                    list_buffer_len = len(list_buffer)
                    logger.debug(f"Pushed {list_buffer_len} songs to upcoming: {list(map(str, list_buffer))}")
                elif index > self.nowplaying_index:
                    # shift upcoming to hist
                    debug_list = self.upcoming[:index - self.nowplaying_index]
                    for _ in range(index - self.nowplaying_index):
                        entry = self.upcoming[0]
                        self.upcoming.remove(0)
                        await self.history.put(entry)
                        debug_list_len = len(debug_list)
                    logger.debug(f"Pushed {debug_list_len} songs to history: {list(map(str, debug_list))}")
            except Exception as e:
                logger.error(e)
                raise
        else:
            raise IndexError()
        
    def get_now_song(self):
        """Pull the last entry (nowplaying song) from history. Removes the entry from queue."""
        if not self.history_empty:
            try:
                nowplaying_song = self.history[-1]
                self.history.remove(-1)
            except IndexError:
                raise IndexError()
            else:
                return nowplaying_song
            
    def get_now_and_prev_songs(self):
        """Pull the last 2 entries (prev, nowplaying song) from history. Removes the entries from queue."""
        if self.previous_playable:
            try:
                nowplaying_song = self.history[-1]
                prev_song = self.history[-2]
                self.history.remove(-1) # Removing last 2 songs by using the last index for both
                self.history.remove(-1)
            except IndexError:
                raise IndexError()
            else:
                return (nowplaying_song, prev_song)
            
    def shuffle_upcoming(self):
        self.upcoming.shuffle()
        
    def clear_all_queues(self):
        self.upcoming.clear()
        self.history.clear()
        
    def clear_upcoming_queue(self):
        self.upcoming.clear()
        
    def remove_song(self, index: int):
        index = 1 if index < 1 else index
        index = len(self._playlist) if index > len(self._playlist) else index
        
        if index <= self.nowplaying_index:
            return self.history.remove(index - 1)
        else:
            index = index - self.nowplaying_index
            return self.upcoming.remove(index - 1)
    
    async def remove_requesters(self, requesters_to_remove: list):
        """remove *all* songs from the mentioned person"""
        try:
            start = time.perf_counter_ns()
            modified_playlist = []
            count = 0
            new_nowplaying_idx = 0
            for idx, song in enumerate(self._playlist[:]):
                if song.requester.id not in requesters_to_remove:
                    modified_playlist.append(song)
                else:
                    count +=1
                if idx == self.nowplaying_index - 1:
                    new_nowplaying_idx = len(modified_playlist)
            self.clear_all_queues()
            await self.push_entry(modified_playlist)
            if not new_nowplaying_idx == 0:
                await self.shift_queues_to(new_nowplaying_idx)
            end = time.perf_counter_ns()
            logger.debug(f"Took [{end-start}] nanoseconds to remove requesters")
            return count
        except Exception as e:
            logger.error(e)
            raise
        
    async def remove_dupes(self):
        """remove *all* repeated songs (leave the first occurrence alone)"""
        try:
            start = time.perf_counter_ns()
            modified_playlist = []
            count = 0
            new_nowplaying_idx = 0
            url_set = {}
            for idx, song in enumerate(self._playlist[:]):
                if song.url not in url_set:
                    modified_playlist.append(song)
                    url_set.add(song.url)
                else:
                    count +=1
                if idx == self.nowplaying_index - 1:
                    new_nowplaying_idx = len(modified_playlist)
            self.clear_all_queues()
            await self.push_entry(modified_playlist)
            if not new_nowplaying_idx == 0:
                await self.shift_queues_to(new_nowplaying_idx)
            end = time.perf_counter_ns()
            logger.debug(f"Took [{end-start}] nanoseconds to remove dupes")
            return count
        except Exception as e:
            logger.error(e)
            raise
        
    async def remove_absent(self, present_members: list):
        """remove *only upcoming* songs from users not in the voice channel"""
        try:
            start = time.perf_counter_ns()
            modified_playlist = []
            count = 0
            for song in self.upcoming[:]:
                if song.requester.id in present_members:
                    modified_playlist.append(song)
                else:
                    count +=1
            self.clear_upcoming_queue()
            await self.push_entry(modified_playlist)
            end = time.perf_counter_ns()
            logger.debug(f"Took [{end-start}] seconds to remove songs by absent users")
            return count
        except Exception as e:
            logger.error(e)
            raise
        
    async def move_song(self, old_idx: int, new_idx: int):
        # indice sanitization
        old_idx = 1 if old_idx < 1 else old_idx
        old_idx = len(self._playlist) if old_idx > len(self._playlist) else old_idx
        new_idx = 1 if new_idx < 1 else new_idx
        new_idx = len(self._playlist) if new_idx > len(self._playlist) else new_idx
            
        moving_nowplaying_song = False
        try:
            if old_idx == self.nowplaying_index:
                moving_nowplaying_song = True
            
            if old_idx <= self.nowplaying_index:
                item = self.history[old_idx - 1]
                self.history.remove(old_idx - 1)
            else:
                item = self.upcoming[old_idx - self.nowplaying_index - 1]
                self.upcoming.remove(old_idx - self.nowplaying_index - 1)
        except IndexError:
            raise IndexError()
        else:
            if new_idx <= self.nowplaying_index:
                self.history.insert(new_idx - 1, item)
            else:
                self.upcoming.insert(new_idx - self.nowplaying_index - 1, item)
            
            if moving_nowplaying_song == True:
                await self.shift_queues_to(new_idx)

class VoiceState:
    """Class defining a music player that uses a queue"""
    #__slots__ = ('bot', '_ctx', '_guild', '_channel', '_cog', 'current', 'voice', 'next', 'songs', 'history', 'queuebuffer', '_bufferflag', '_loop', '_volume', '_send_embed', 'audio_player')
    
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog
        
        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.playlist = Playlist()
        
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
    def playlist_empty(self):
        return self.playlist.playlist_empty
    
    @property
    def upcoming_empty(self):
        return self.playlist.upcoming_empty
    
    @property
    def previous_playable(self):
        return self.playlist.previous_playable
    
    @property
    def nowplaying_index(self):
        return self.playlist.nowplaying_index

    async def push_entry(self, source, pushTopFlag: bool = False):
        await self.playlist.push_entry(source, pushTopFlag)

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
                        self.current = await self.playlist.get()
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
                
                await self.playlist.put_history(self.current)
                await self.next.wait()
                logger.debug("Done playing the song")
                if self.voice is not None:
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
        try:
            if index > self.playlist.nowplaying_index:
                await self.playlist.shift_queues_to(index - 1)
            elif index < self.playlist.nowplaying_index:
                await self.playlist.shift_queues_to(index - 1)
            else:
                return
        except Exception as e:
            raise e
        else:
            self.skip_song()
        
    async def previous_song(self):
        if self.previous_playable:
            try:
                nowplaying_song, prev_song = self.playlist.get_now_and_prev_songs()
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
            song = self.playlist.prev_song
            if isinstance(song, YTDLMetadata):
                return song.create_embed()
            else:
                newsource = await YTDLSource.create_source(song.ctx, song.url, loop = self.bot.loop)
                song = YTDLMetadata(newsource.ctx, newsource.data)
                return song.create_embed()
    
    def current_info_embed(self):
        return self.current.create_embed()
    
    async def next_info_embed(self):
        if not self.upcoming_empty:
            song = self.playlist.next_song
            if isinstance(song, YTDLMetadata):
                return song.create_embed()
            else:
                newsource = await YTDLSource.create_source(song.ctx, song.url, loop = self.bot.loop)
                song = YTDLMetadata(newsource.ctx, newsource.data)
                return song.create_embed()
    
    def shuffle_queue(self):
        self.playlist.shuffle_upcoming()
        
    def remove_song(self, index: int):
        return self.playlist.remove_song(index)
        
    async def remove_requesters(self, requesters_to_remove: list):
        try:
            count = await self.playlist.remove_requesters(requesters_to_remove)
            return count
        except Exception as e:
            raise
        
    async def remove_dupes(self):
        try:
            count = await self.playlist.remove_dupes()
            return count
        except Exception as e:
            raise
    
    async def remove_absent(self, present_members: list):
        try:
            count = await self.playlist.remove_absent()
            return count
        except Exception as e:
            raise
    
    def clear_queue(self):
        self.playlist.clear_all_queues()
        
    async def move_song(self, old_idx: int, new_idx: int):
        return await self.playlist.move_song(old_idx, new_idx)
    
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
            nowplaying_song = self.playlist.get_now_song()
        except IndexError:
            raise IndexError()
        else:
            if nowplaying_song is not None:
                await self.push_entry([nowplaying_song], pushTopFlag = True)
        await asyncio.sleep(1)
        self.audio_player_task.start()
    
    async def stop(self):
        self.clear_queue()
        
        if self.voice:
            await self.voice.disconnect()
            self.voice = None
            self.current = None
