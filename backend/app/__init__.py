"""SlopShots backend package.

The package initializer intentionally does not import the ASGI application.
Importing a helper such as ``app.models`` must not construct a ``JobStore`` or
create directories on disk.  The ASGI entry point remains ``app.main:app``.
"""

__all__: list[str] = []
