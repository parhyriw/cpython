import gc
import random
import sys
import threading
import time
import weakref

# -- Sanity check ------------------------------------------------------------
if sys.version_info < (3, 14):
    raise RuntimeError("Requires CPython 3.14+")

# -- Configuration ------------------------------------------------------------
NUM_THREADS = 16  # worker threads (no GIL -> true parallelism)
OBJECT_POOL_SIZE = 50_000  # live objects in the shared pool at any time
MUTATION_RATE = 0.3  # fraction of pool replaced per cycle
CYCLE_SLEEP = 0.0  # seconds between cycles (0 = full speed)
DURATION_SECONDS = 60  # total run time
WEAKREF_FRACTION = 0.2  # fraction of pool also held as weakrefs
DEEP_CYCLE_DEPTH = 8  # depth of reference cycles injected
ENABLE_GC_CALLBACKS = True  # register gc callbacks (tracked from inside too)

# -- Shared mutable state (deliberately racy without the GIL) -----------------
pool_lock = threading.Lock()
shared_pool: list = []  # list of live objects - threads read & write this

# -- Object types that stress different GC paths ------------------------------


class Node:
    """Doubly-linked node - forms cycles naturally."""

    __slots__ = ("value", "left", "right", "payload")

    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None
        self.payload = bytearray(random.randint(64, 512))  # varied size


class RefCycle:
    """Explicit reference cycle: a -> b -> a."""

    def __init__(self, depth=DEEP_CYCLE_DEPTH):
        head = self
        current = self
        for _ in range(depth):
            nxt = RefCycle.__new__(RefCycle)
            nxt.child = None
            nxt.parent = current
            current.child = nxt  # type: ignore[attr-defined]
            current = nxt
        current.child = head  # close the cycle


class SharedDict:
    """Dict mutated by multiple threads simultaneously."""

    def __init__(self):
        self.data: dict[int, object] = {i: Node(i) for i in range(50)}
        self.lock = threading.Lock()

    def mutate(self):
        key = random.randint(0, 49)
        with self.lock:
            self.data[key] = Node(key)


# One instance shared by all threads
shared_dict = SharedDict()

# Weakref set - lets us observe object death without preventing collection
weak_pool: list[weakref.ref] = []
weak_lock = threading.Lock()

# -- GC callbacks (internal measurement, for cross-reference only) -------------
gc_event_log: list[tuple[str, float]] = []  # (phase, timestamp)
gc_log_lock = threading.Lock()


# -- Worker functions ----------------------------------------------------------


def make_linked_list(length: int = 200) -> Node:
    """Create a chain of Nodes (no cycles)."""
    head = Node(0)
    cur = head
    for i in range(1, length):
        nxt = Node(i)
        cur.right = nxt
        nxt.left = cur
        cur = nxt
    return head


def make_cycle_cluster(n: int = 20) -> list:
    """Return a list of RefCycle objects that form a cross-linked cluster."""
    cycles = [RefCycle() for _ in range(n)]
    # Cross-link them so the GC has to trace a complex subgraph
    for i, c in enumerate(cycles):
        c.sibling = cycles[(i + 1) % n]  # type: ignore[attr-defined]
    return cycles


def replace_pool_slice(count: int):
    """Replace `count` random entries in the shared pool with new objects."""
    new_objects: list = []
    for _ in range(count):
        kind = random.random()
        if kind < 0.4:
            new_objects.append(make_linked_list(random.randint(50, 400)))
        elif kind < 0.7:
            new_objects.append(make_cycle_cluster(random.randint(5, 30)))
        else:
            new_objects.append(
                {i: Node(i) for i in range(random.randint(20, 100))}
            )

    indices = random.sample(
        range(len(shared_pool)), min(count, len(shared_pool))
    )
    with pool_lock:
        for idx, obj in zip(indices, new_objects):
            shared_pool[idx] = obj


def worker_mutate(stop_event: threading.Event):
    """Continuously mutate the shared pool and shared_dict."""
    count = int(OBJECT_POOL_SIZE * MUTATION_RATE / NUM_THREADS)
    while not stop_event.is_set():
        replace_pool_slice(count)
        shared_dict.mutate()
        # Occasionally add weakrefs
        if random.random() < WEAKREF_FRACTION:
            with pool_lock:
                obj = random.choice(shared_pool)
            try:
                wr = weakref.ref(obj)
                with weak_lock:
                    if len(weak_pool) > 10_000:
                        weak_pool.clear()
                    weak_pool.append(wr)
            except TypeError:
                pass
        if CYCLE_SLEEP > 0:
            time.sleep(CYCLE_SLEEP)


def worker_reader(stop_event: threading.Event):
    """Read-traverse the shared pool to keep objects 'alive' and in use."""
    while not stop_event.is_set():
        with pool_lock:
            if not shared_pool:
                continue
            sample = random.sample(shared_pool, min(200, len(shared_pool)))
        # Traverse without the lock held - this is the racy part
        acc = 0
        for obj in sample:
            if isinstance(obj, Node):
                cur = obj
                for _ in range(20):
                    if cur.right is None:
                        break
                    cur = cur.right
                    acc += cur.value
            elif isinstance(obj, list):
                for c in obj:
                    acc += id(c) & 0xFF
            elif isinstance(obj, dict):
                for v in obj.values():
                    acc += id(v) & 0xFF
        # Sink so the compiler can't elide the traversal
        if acc < 0:
            print("(impossible)")


def worker_gc_trigger(stop_event: threading.Event):
    """Periodically force full GC collections."""
    while not stop_event.is_set():
        time.sleep(0.05)
        gc.collect(2)  # generation 2 -> most expensive collection


# -- Main ----------------------------------------------------------------------


def main():
    print(f"[stress] Python {sys.version}", flush=True)
    print(
        f"[stress] GIL status: {getattr(sys, '_is_gil_enabled', lambda: 'unknown')()}",
        flush=True,
    )
    print(
        f"[stress] Threads: {NUM_THREADS}  Pool: {OBJECT_POOL_SIZE}  Duration: {DURATION_SECONDS}s",
        flush=True,
    )

    # Pre-populate pool
    print("[stress] Populating initial pool...", flush=True)
    with pool_lock:
        for _ in range(OBJECT_POOL_SIZE):
            shared_pool.append(make_linked_list(100))
    print("[stress] Pool ready. Starting threads...", flush=True)

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    # Mutator threads (majority)
    n_mut = NUM_THREADS * 2 // 3
    for _ in range(n_mut):
        t = threading.Thread(
            target=worker_mutate, args=(stop_event,), daemon=True
        )
        threads.append(t)

    # Reader threads
    n_read = NUM_THREADS - n_mut - 1
    for _ in range(n_read):
        t = threading.Thread(
            target=worker_reader, args=(stop_event,), daemon=True
        )
        threads.append(t)

    # One dedicated GC-trigger thread
    threads.append(
        threading.Thread(
            target=worker_gc_trigger, args=(stop_event,), daemon=True
        )
    )

    for t in threads:
        t.start()

    print(
        f"[stress] All {len(threads)} threads running. Test ends in {DURATION_SECONDS}s.",
        flush=True,
    )
    time.sleep(DURATION_SECONDS)
    stop_event.set()

    for t in threads:
        t.join(timeout=5)

    print("[stress] Done.")
    exit()


if __name__ == "__main__":
    main()
