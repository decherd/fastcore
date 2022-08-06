# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03a_parallel.ipynb.

# %% auto 0
__all__ = ['threaded', 'startthread', 'parallelable', 'ThreadPoolExecutor', 'ProcessPoolExecutor', 'parallel', 'add_one',
           'run_procs', 'parallel_gen']

# %% ../nbs/03a_parallel.ipynb 1
from .imports import *
from .basics import *
from .foundation import *
from .meta import *
from .xtras import *
from functools import wraps

import concurrent.futures,time
from multiprocessing import Process,Queue,Manager,set_start_method,get_all_start_methods,get_context
from threading import Thread
try:
    if sys.platform == 'darwin' and IN_NOTEBOOK: set_start_method("fork")
except: pass

# %% ../nbs/03a_parallel.ipynb 4
def threaded(f):
    "Run `f` in a thread, and returns the thread"
    @wraps(f)
    def _f(*args, **kwargs):
        res = Thread(target=f, args=args, kwargs=kwargs)
        res.start()
        return res
    return _f

# %% ../nbs/03a_parallel.ipynb 6
def startthread(f):
    "Like `threaded`, but start thread immediately"
    threaded(f)()

# %% ../nbs/03a_parallel.ipynb 8
def _call(lock, pause, n, g, item):
    l = False
    if pause:
        try:
            l = lock.acquire(timeout=pause*(n+2))
            time.sleep(pause)
        finally:
            if l: lock.release()
    return g(item)

# %% ../nbs/03a_parallel.ipynb 9
def parallelable(param_name, num_workers, f=None):
    f_in_main = f == None or sys.modules[f.__module__].__name__ == "__main__"
    if sys.platform == "win32" and IN_NOTEBOOK and num_workers > 0 and f_in_main:
        print("Due to IPython and Windows limitation, python multiprocessing isn't available now.")
        print(f"So `{param_name}` has to be changed to 0 to avoid getting stuck")
        return False
    return True

# %% ../nbs/03a_parallel.ipynb 10
class ThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    "Same as Python's ThreadPoolExecutor, except can pass `max_workers==0` for serial execution"
    def __init__(self, max_workers=defaults.cpus, on_exc=print, pause=0, **kwargs):
        if max_workers is None: max_workers=defaults.cpus
        store_attr()
        self.not_parallel = max_workers==0
        if self.not_parallel: max_workers=1
        super().__init__(max_workers, **kwargs)

    def map(self, f, items, *args, timeout=None, chunksize=1, **kwargs):
        if self.not_parallel == False: self.lock = Manager().Lock()
        g = partial(f, *args, **kwargs)
        if self.not_parallel: return map(g, items)
        _g = partial(_call, self.lock, self.pause, self.max_workers, g)
        try: return super().map(_g, items, timeout=timeout, chunksize=chunksize)
        except Exception as e: self.on_exc(e)

# %% ../nbs/03a_parallel.ipynb 12
@delegates()
class ProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    "Same as Python's ProcessPoolExecutor, except can pass `max_workers==0` for serial execution"
    def __init__(self, max_workers=defaults.cpus, on_exc=print, pause=0, **kwargs):
        if max_workers is None: max_workers=defaults.cpus
        store_attr()
        self.not_parallel = max_workers==0
        if self.not_parallel: max_workers=1
        super().__init__(max_workers, **kwargs)

    def map(self, f, items, *args, timeout=None, chunksize=1, **kwargs):
        if not parallelable('max_workers', self.max_workers, f): self.max_workers = 0
        self.not_parallel = self.max_workers==0
        if self.not_parallel: self.max_workers=1

        if self.not_parallel == False: self.lock = Manager().Lock()
        g = partial(f, *args, **kwargs)
        if self.not_parallel: return map(g, items)
        _g = partial(_call, self.lock, self.pause, self.max_workers, g)
        try: return super().map(_g, items, timeout=timeout, chunksize=chunksize)
        except Exception as e: self.on_exc(e)

# %% ../nbs/03a_parallel.ipynb 14
try: from fastprogress import progress_bar
except: progress_bar = None

# %% ../nbs/03a_parallel.ipynb 15
def parallel(f, items, *args, n_workers=defaults.cpus, total=None, progress=None, pause=0,
             method=None, threadpool=False, timeout=None, chunksize=1, **kwargs):
    "Applies `func` in parallel to `items`, using `n_workers`"
    kwpool = {}
    if threadpool: pool = ThreadPoolExecutor
    else:
        if not method and sys.platform == 'darwin' and not IN_NOTEBOOK: method='spawn'
        if method: kwpool['mp_context'] = get_context(method)
        pool = ProcessPoolExecutor
    with pool(n_workers, pause=pause, **kwpool) as ex:
        r = ex.map(f,items, *args, timeout=timeout, chunksize=chunksize, **kwargs)
        if progress and progress_bar:
            if total is None: total = len(items)
            r = progress_bar(r, total=total, leave=False)
        return L(r)

# %% ../nbs/03a_parallel.ipynb 16
def add_one(x, a=1):
    # this import is necessary for multiprocessing in notebook on windows
    import random
    time.sleep(random.random()/80)
    return x+a

# %% ../nbs/03a_parallel.ipynb 21
def run_procs(f, f_done, args):
    "Call `f` for each item in `args` in parallel, yielding `f_done`"
    processes = L(args).map(Process, args=arg0, target=f)
    for o in processes: o.start()
    yield from f_done()
    processes.map(Self.join())

# %% ../nbs/03a_parallel.ipynb 22
def _f_pg(obj, queue, batch, start_idx):
    for i,b in enumerate(obj(batch)): queue.put((start_idx+i,b))

def _done_pg(queue, items): return (queue.get() for _ in items)

# %% ../nbs/03a_parallel.ipynb 23
def parallel_gen(cls, items, n_workers=defaults.cpus, **kwargs):
    "Instantiate `cls` in `n_workers` procs & call each on a subset of `items` in parallel."
    if not parallelable('n_workers', n_workers): n_workers = 0
    if n_workers==0:
        yield from enumerate(list(cls(**kwargs)(items)))
        return
    batches = L(chunked(items, n_chunks=n_workers))
    idx = L(itertools.accumulate(0 + batches.map(len)))
    queue = Queue()
    if progress_bar: items = progress_bar(items, leave=False)
    f=partial(_f_pg, cls(**kwargs), queue)
    done=partial(_done_pg, queue, items)
    yield from run_procs(f, done, L(batches,idx).zip())
