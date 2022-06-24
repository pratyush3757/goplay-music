import discord
import yt_dlp
import asyncio
import functools

from discord.ext import commands

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda: ''

class VoiceError(Exception):
    pass

class YTDLError(Exception):
    pass

class YTDLMetadata():
    """Class to contain full Metadata about the song, extracted from youtube_dl"""
    __Slots__ = ('requester', 'channel', 'ctx', 'uploader', 'uploader_url', 'date', 'title', 'thumbnail', 'duration' , 'url')
    def __init__(self, ctx: commands.Context, data: dict):
        self.requester = ctx.author
        self.channel = ctx.channel
        self.ctx = ctx
        
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.url = data.get('webpage_url')
        
    def __str__(self):
        return f'**{self.title}** by **{self.uploader}**'
    
    def create_embed(self):
        embed = (discord.Embed(title = "Now Playing",
                               description = f"```css\n{self.title}\n```",
                               color = discord.Color.magenta())
                .add_field(name = "Duration", value = self.duration)
                .add_field(name = "Requested by", value = self.requester.mention)
                .add_field(name = "Uploader", value = f"[{self.uploader}]({self.uploader_url})")
                .add_field(name = "URL", value = f"[Click]({self.url})")
                .set_thumbnail(url = self.thumbnail))
        
        return embed
    
    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        duration = []
        if days > 0:
            duration.append(f"{days} days")
        if hours > 0:
            duration.append(f"{hours} hours")
        if minutes > 0:
            duration.append(f"{minutes} minutes")
        if seconds > 0:
            duration.append(f"{seconds} seconds")
            
        return ', '.join(duration)

class BasicMetadata():
    """Class to contain only basic data about the link"""
    __Slots__ = ('requester', 'channel', 'ctx', 'url', 'title')
    
    def __init__(self, ctx: commands.Context, url: str, title: str):
        self.requester = ctx.author
        self.channel = ctx.channel
        self.ctx = ctx
        
        self.url = url
        self.title = title

    def __str__(self):
        return f'**{self.title}** by **{self.uploader}**'

class YTDLExtractorFlat():
    """Youtube_dl extractor for links and playlists"""
    YTDL_FORMAT_OPTIONS_FLAT = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'extract_flat': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
    }
    
    ytdl_flat = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS_FLAT)
    
    @classmethod
    async def fetch_metadata(cls, ctx: commands.Context, link: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        
        if ('watch' in link) and ('&list' in link): # Handle links with video as well as playlist params
            idx = link.find('&list')
            link = link[:idx]
        
        partial = functools.partial(cls.ytdl_flat.extract_info, link, download = False, process = False)
        data = await loop.run_in_executor(None, partial)
        
        if data is None:
            raise YTDLError(f"Couldn't find anything that matches {link}")
        
        if 'entries' not in data:       # The link is for a single video
            metadata_object = YTDLMetadata(ctx, data)
            return metadata_object
        else:                           # The link is for a playlist
            url_list = []
            for entry in data['entries']:
                url_list.append(BasicMetadata(ctx, url = entry['url'], title = entry['title']))
            return url_list

class YTDLExtractorNonFlat():
    """Youtube_dl extractor for search strings"""
    YTDL_FORMAT_OPTIONS_NONFLAT = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        #'extract_flat': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
    }
    
    ytdl_nonflat = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS_NONFLAT)
    
    @classmethod
    async def fetch_metadata(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        
        partial = functools.partial(cls.ytdl_nonflat.extract_info, search, download = False)
        data = await loop.run_in_executor(None, partial)
        
        if data is None:
            raise YTDLError(f"Couldn't find anything that matches {link}")
        
        if 'entries' not in data:   
            # As non flat extractor always gives 'entries' field with a single item in it, if they are not present
            # we need to send the url field in the parent dict. This part of code is just handler for an impossible edge case.
            raise YTDLError(f"Extractor Results Key Error: There were errors in processing the search results")
        else:
            metadata_object = YTDLMetadata(ctx, data['entries'][0])
            return metadata_object

class YTDLSource():
    """Youtube_dl based ffmpeg source for audio.
        Extracts the stream url from a link and creates the source"""
    YTDL_FORMAT_OPTIONS = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        #'extract_flat': True,
        #'skip_download': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
    }
    
    FFMPEG_OPTIONS = {
        'before_options':'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }
    
    ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
    
    def __init__(self, ctx: commands.Context, source: discord.FFmpegOpusAudio, *, data: dict):
        self.audio_source = source
        self.ctx = ctx
        self.data = data
    
    @classmethod
    async def create_source(cls, ctx: commands.Context, link: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()
        
        partial = functools.partial(cls.ytdl.extract_info, link, download=False)
        processed_info = await loop.run_in_executor(None, partial)
        
        if processed_info is None:
            raise YTDLError(f"Couldn't fetch {link}")
        
        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(f"Couldn't retrieve any matches for {link}")
        
        ffmpeg_source = await discord.FFmpegOpusAudio.from_probe(info['url'], **cls.FFMPEG_OPTIONS)
        return cls(ctx, ffmpeg_source, data=info)
    
