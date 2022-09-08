from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class User:

    @classmethod
    def from_json(cls, uj):
        return cls()


@dataclass
class Track:
    title: str
    artwork_url: str
    bpm: int
    comment_count: int
    commentable: bool
    created_at: str
    description: str
    download_count: int
    downloadable: str
    duration: int
    embeddable_by: str
    favoritings_count: int
    genre: str
    id: int
    isrc: str
    key_signature: str
    kind: str
    label_name: str
    license: str
    permalink_url: str
    playback_count: int
    purchase_title: str
    purchase_url: str
    release: str
    release_day: int
    release_month: int
    release_year: int
    sharing: str
    stream_url: str
    streamable: bool
    tag_list: str
    uri: str
    user: User
    user_favorite: bool
    user_playback_count: int
    waveform_url: str
    available_country_codes: str
    access: Optional[Literal['playable', 'preview', 'blocked']]
    download_url: str
    reposts_count: int
    secret_uri: str

    @classmethod
    def from_json(cls, tj):
        tj['user'] = User.from_json(tj['user'])
        return cls(
            **tj
        )


@dataclass
class Tracks:
    collection: list[Track]
    next_href: str

    @classmethod
    def from_json(cls, tracks_json):
        collection = [
            Track.from_json(t_json) for t_json in tracks_json['collection']
        ]
        return cls(
            collection,
            tracks_json['next_href']
        )
