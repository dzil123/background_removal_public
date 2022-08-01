import traceback
from concurrent.futures import ThreadPoolExecutor

import wx
from PIL import Image
from pubsub import pub

import rembg
from rembg.session_factory import new_session

from .model import File, Session, Status


def msg(*args, **kwargs):
    wx.CallAfter(pub.sendMessage, *args, **kwargs)


# run in thread
def load_session():
    model_session = new_session("u2net")
    pool = ThreadPoolExecutor(8)
    return Session(model_session=model_session, pool=pool)


# nonblocking
def queue_file(session: Session, file: File):
    future = session.pool.submit(do_work, session, file)
    future.add_done_callback(done_callback)


def do_work(session: Session, file: File):
    file.status = Status.Running
    msg("update_files")

    try:
        with Image.open(file.file) as image:
            with rembg.remove(image, session=session.model_session) as out_image:
                file.outfile.parent.mkdir(parents=True, exist_ok=True)
                out_image.save(file.outfile)
    except Exception:
        file.status = Status.Error
        msg("fatalError", ctx=file, e=traceback.format_exception(*sys.exc_info()))
        raise
    else:
        file.status = Status.Done
        msg("update_files")


def done_callback(future):
    future.result()  # raise exception
