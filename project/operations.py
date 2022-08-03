import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

import wx
from PIL import Image
from pubsub import pub

import rembg
import rembg.session_factory

from .model import File, ModelType, Session, Settings, Status


def msg(*args, **kwargs):
    wx.CallAfter(pub.sendMessage, *args, **kwargs)


class CustomThread(Thread):
    def __init__(self, func):
        super().__init__(daemon=True)
        self.func = func
        self.start()

    def run(self, *args):
        try:
            self.func()
        except Exception:
            msg(
                "fatalError",
                e=traceback.format_exception(*sys.exc_info()),
                ctx=self.func.__name__,
            )
            raise


def new_session():
    model_sessions = None
    pool = ThreadPoolExecutor(8)
    discover_pool = ThreadPoolExecutor(1)
    session = Session(
        model_sessions=model_sessions, pool=pool, discover_pool=discover_pool
    )
    return session


def load_model_sessions():
    CustomThread(_load_model_sessions)


def _load_model_sessions():
    model_sessions = {}

    with ThreadPoolExecutor(1) as pool:
        for model in ModelType:
            pool.submit(__load_model_sessions, model_sessions, model.name)
    __import__("time").sleep(10)
    assert len(model_sessions) == len(ModelType)
    msg("model_sessions_loaded", model_sessions=model_sessions)


def __load_model_sessions(model_sessions, model):
    try:
        model_sessions[model] = rembg.session_factory.new_session(model)
    except Exception:
        msg(
            "fatalError",
            ctx=f"model {model}",
            e=traceback.format_exception(*sys.exc_info()),
        )
        raise


def queue_discover(session: Session, iterator):
    session.discover_pool.submit(_queue_discover, iterator)


def _queue_discover(iterator):
    for file, outfile in iterator:
        msg("discoverFile", file=file, outfile=outfile)
    msg("discoverDone")


# nonblocking
def queue_file(session: Session, file: File, settings: Settings):
    future = session.pool.submit(do_work, session, file, settings)
    future.add_done_callback(done_callback)


def do_work(session: Session, file: File, settings: Settings):
    file.status = Status.Running
    msg("update_files")

    try:
        session = session.model_sessions[settings.model.name]
        with Image.open(file.file) as image:
            out_image = rembg.remove(image, session=session)
        new_image = Image.new("RGBA", out_image.size, settings.bgcolor.value)
        new_image = Image.alpha_composite(new_image, out_image)
        file.outfile.parent.mkdir(parents=True, exist_ok=True)
        new_image.save(file.outfile)
    except Exception:
        file.status = Status.Error
        msg("fatalError", ctx=file, e=traceback.format_exception(*sys.exc_info()))
        raise
    else:
        file.status = Status.Done
        msg("update_files")


def done_callback(future):
    future.result()  # raise exception
