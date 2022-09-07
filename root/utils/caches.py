import time
from collections import deque


class MusicListCache:
    def __init__(self, page_size: int):
        self.cache: dict[str, list[]] = {}
        self.cache_life = deque(maxlen=128)
        self.page_size = page_size

    def get(self, key: str, page: int):
        if key in self.cache and page * self.page_size <= len(self.cache[key][1]):
            musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page - 1) * 9:current_page * 9]
            NEXT_PAGE_FLAG = True
            if len(musiclist) < MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False

    # cache functions
    def get_cache(self, key):
        self.cache[key][0].replant(time.time() + 60 * 5)
        return self.cache[key][1]

    async def caching_list(vk_audio, request):
        if request in MUSICLIST_CACHE:
            return
        # bomb on 5 minutes
        bomb = DictionaryBomb(MUSICLIST_CACHE, request, time.time() + 60 * 5)

        if request == "!popular":
            generator = vk_audio.get_popular_iter()
        elif request == "!new_songs":
            generator = vk_audio.get_news_iter()
        else:
            generator = vk_audio.search_iter(request)

        musiclist = []
        MUSICLIST_CACHE[request] = (bomb, musiclist)

        musiclist.append(next(generator))
        for i in range(98):
            try:
                next_track = next(generator)
                if next_track == musiclist[0]:
                    break
                musiclist.append(next_track)
                await asyncio.sleep(0)
            except StopIteration:
                break

        asyncio.create_task(bomb.plant())


class CasheUnit:
    def __init__(self):
        pass