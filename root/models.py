from dataclasses import dataclass


@dataclass
class Track:
    title: str
    performer: str
    duration: int

    @property
    def full_name(self):
        return f'{self.performer} - {self.title}'

    async def load_audio(self) -> bytes | None:
        raise NotImplementedError()

    def get_id(self) -> str:
        raise NotImplementedError()
