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
    model_session: "onnxsession"
    pool: "concurrent.futures.Executor"
