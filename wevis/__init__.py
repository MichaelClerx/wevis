#!/usr/bin/env python3
"""
Server/client module for Where's Ben Nevis.
"""
import sys

# Check Python version
if sys.hexversion < 0x03050000:
    raise RuntimeError('wevis requires Python 3.5 or newer.')

# Wevis version
__version__ = '0.0.2'

# Default port
_DEFAULT_PORT = 12121

# Default initial logging level, or None
_LOGGING_LEVEL = None

#
# Maximum connections per user
#
MAX_CONNECTIONS_PER_USER = 1

#
# Server sleep times (in seconds)
# Note: sleep times should never be 0, although it's OK to set them very very
# small.
#
# Room: Minimum delay between any two commands handled by room.
SSLEEP_ROOM = 1e-6
# Manager: Minimum delay between any two cycles of the manager. In each cycle
#          the manager checks connections are alive, checks if new connections
#          were passed in by the listener, and handles all queued commands.
SSLEEP_MANAGER = 1e-6
# Listener: Delay between two checks for a new connection
SSLEEP_LISTENER = 0.2
# Server launch: Time between two checks that the main thread is running
SSLEEP_LAUNCH = 0.5
# Server: Server only waits for halt signal, sleep time can be long.
SSLEEP_SERVER = 0.5
# Server shutdown: Time to wait for individual threads to shut down
SSLEEP_SHUTDOWN = 1

#
# Client sleep times (in seconds)
#
# Receive a message in blocking mode: time between checks
CSLEEP_RECEIVE_BLOCKING = 1e-8
# Main thread: Minimum delay between any two cycles of the client. In each
#              cycle the client sends and receives messages
CSLEEP_RUN = 1e-8
# Start blocking: Time between checks that the client has started (checks stop
#                 as soon as the client is online).
CSLEEP_START_BLOCKING = 0.1

#
# Shared
#
# When establishing a connection, a "blocking" read is sometimes used which
# keeps checking for a specific message, but sleeps for a bit if nothing's
# found. This is only during e.g. login. Blocking receive in normal client
# operation uses CSLEEP_START_BLOCKING
SLEEP_READ_BLOCKING_INTERNAL = 0.1

#
# Ping/pong times (in seconds)
#
PING_INTERVAL = 10
PING_TIMEOUT = 5
LOGIN_TIMEOUT = 5


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
    global _LOGGING_LEVEL
    _LOGGING_LEVEL = level


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

# Don't expose imported modules as part of the api
del(sys)
