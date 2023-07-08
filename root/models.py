from dataclasses import dataclass


@dataclass
class Track:
    title: str
    performer: str
    duration: int

    async def load_audio(self) -> bytes | None:
        raise NotImplementedError()

    def get_id(self) -> str:
        raise NotImplementedError()
