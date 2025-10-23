import asyncio
from inspect import isawaitable, ismethod


def async_to_sync(coro):
    return asyncio.run(coro)


class AsyncClient:
    def __init__(self, client):
        self.client = async_to_sync(client.__aenter__())

    def __getattr__(self, name):
        attr = getattr(self.client, name)
        if not ismethod(attr):
            return attr

        def wrapper(*args, **kwargs):
            value = attr(*args, **kwargs)
            if isawaitable(value):
                return async_to_sync(value)
            return value

        return wrapper
