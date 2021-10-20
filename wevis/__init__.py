#!/usr/bin/env python3
"""
Server/client module for Where's Ben Nevis.
"""

# Default port
default_port = 12121

# Default initial logging level, or None
logging_level = None


# Shared string hashing function
def encrypt(password, salt):
    """
    Combines the given ``password`` and ``salt`` and returns a string.

    Intended use, client-side:

    - The client receives a ``salt`` string when connecting. The user provides
      a plain text password. The client then calls
      ``encrypt(plain_password, salt)`` to create an encrypted string for
      network transmission.

    And server side:

    - The server receives a new connection, and response by sending ``salt``.
      In return it receives a username and a encrypted string.
    - In a debugging set up, the server looks up the plain text password, calls
      ``encrypt(plain_password, salt)`` and compares the result.
    - In a better set up, the server looks up another ``salt_2`` and another
      encrypted string ``string_2`` and checks whether
      ``encrypt(received_password, salt_2) == string_2``.

    """
    import hashlib
    return hashlib.sha512(
        (str(password) + str(salt)).encode('utf-8')).hexdigest()


def set_logging_level(level=None):
    """
    Determines the default logging level set when creating new
    ``logging.Logger`` objects inside wevis threads (e.g. the Server).

    If set to ``None`` (the default), the loggers are kept at their default
    levels.

    Loggers of individual threads can be accessed using their ``log`` property.
    """
    global logging_level
    logging_level = level


# Build public API
from ._message import (  # noqa
    DefinitionList,
    Message,
    MessageDefinition,
    MessageReader,
    MessageWriter,
    SocketClosedError
)
from ._user import (     # noqa
    User,
)
from ._server import (   # noqa
    Room,
    Server,
)
from ._client import (   # noqa
    Client,
)


# Define server messages
MessageDefinition('_ping')
MessageDefinition('_pong')
MessageDefinition('_welcome', salt=str)
MessageDefinition('_login', username=str, password=str,
                  # TODO: Use vector of ints?
                  major=int, minor=int, revision=int)
MessageDefinition('_loginReject', reason=str)
MessageDefinition('_loginAccept')

