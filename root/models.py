from dataclasses import dataclass


@dataclass
class Track:
    title: str
    performer: str
    duration: int

    async def load_audio(self):
        raise NotImplementedError()
