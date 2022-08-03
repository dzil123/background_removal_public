from dataclasses import dataclass
from enum import Enum

Status = Enum("Status", "Error Running Pending Done")


@dataclass
class File:
    file: str
    outfile: str
    status: Status


@dataclass
class Session:
    model_sessions: None
    pool: None
    discover_pool: None


class BGColor(Enum):
    Transparent = (0, 0, 0, 0)
    White = (255, 255, 255, 255)
    Black = (0, 0, 0, 255)
    Green = (0, 255, 0, 255)


BGColorList = [bgcolor.name for bgcolor in BGColor]

ModelType = Enum("ModelType", "u2net u2netp u2net_human_seg u2net_cloth_seg")

ModelTypeList = [model.name for model in ModelType]


@dataclass
class Settings:
    bgcolor = BGColor.Green
    model = ModelType.u2net
