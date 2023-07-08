from dataclasses import dataclass


@dataclass(frozen=True)
class Constants:
    MEGABYTE_SIZE = 1 << 20
    MUSIC_LIST_LENGTH = 5
