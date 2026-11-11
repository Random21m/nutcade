class _D(type):
    def __getattr__(cls, n): return _D(n, (object,), {})
class EventListener(metaclass=_D): pass
def __getattr__(n): return _D(n, (object,), {})
