#!/usr/bin/env python3
"""
Server code for Where's Ben Nevis.
"""
import logging
import queue
import random
import socket
import threading
import time

import wevis


class Server(threading.Thread):
    """
    Sets up a server that creates a :class`Listener` to accept connections from
    new clients and a :class:`Manager` to handle active connections.

    Arguments:

    ``version_validator``
        A callable that will be called with integer arguments
        ``(major, minor, revision)`` to test if new connections are compatible
        with the current version. Should return ``True`` if so, or ``False`` if
        the client needs to be updated.
    ``user_validator``
        A callable that will be called with ``(username, password, salt)`` to
        test if user credentials are valid. The ``username`` will be a plain
        text username, and ``password`` and ``salt`` will be such that calling
        :meth:`encrypt(plain_password, salt)` returns ``password``. If the
        credentials are OK, the callable should return an instance of
        :class:`User` (which may be a subclass). If not, ``None`` should be
        returned.
    ``room``
        A :class:`wevis.Room` instance to handle incoming messages.
    ``host``
        The hostname this server is running on (or ``None`` to autodetect).
    ``port``
        The port to listen on (or ``None`` for the default).
    ``name``
        A name to use for the Server's thread and logger.

    """

    PRE_RUN = 0
    RUNNING = 1
    POST_RUN = 2

    def __init__(self, version_validator, user_validator, room,
                 host=None, port=None, name='wevis.server'):
        super().__init__(name=name)

        # Logging
        self._log = logging.getLogger(name)
        if wevis._LOGGING_LEVEL is not None:
            self._log.setLevel(wevis._LOGGING_LEVEL)
        self._log.info(f'Creating server. Using wevis {wevis.__version__}')

        # Status
        self._status = Server.PRE_RUN

        # User and version validation
        self._version_validator = version_validator
        self._user_validator = user_validator
        del(version_validator, user_validator)

        # Room (can be extended to multiple, multiprocessing/distributed in the
        # future).
        if not isinstance(room, wevis.Room):
            raise ValueError('Given room must be a wevis.Room')
        self._room = room
        self._room.set_server(self)
        del(room)

        # Host and port
        self._host = host if host else socket.gethostname()
        self._port = port if port else wevis._DEFAULT_PORT
        del(host, port)

        # Create socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Tell socket to re-use socket address without waiting for time-out.
        # This is useful for quickly restarting the server: Once a call to
        # listen is made the socket is unavailable until the timeout has
        # passed. When restarting it can happen that the timeout period isn't
        # over yet.
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Set socket to non-blocking mode
        self._sock.setblocking(False)

        # Bind socket
        self._log.info(f'Listening on {self._host}:{self._port}')
        self._sock.bind((self._host, self._port))

        # Run as background process
        self.setDaemon(True)

        # Event used to halt the server
        self._halt = threading.Event()

        # Exception the server crashed with (if any)
        self._exception = None

        # Create manager and listener
        self._log.info('Creating manager')
        self._manager = Manager(self)

        self._log.info('Creating listener')
        self._listener = Listener(self, self._manager)

    @property
    def halt_event(self):
        """ Returns a flag that can be set to shut the server down. """
        return self._halt

    def launch(self):
        """
        Starts this server, and continues until an exception occurs (e.g. a
        ``KeyboardInterrupt``).
        """
        self.start()
        try:
            while self.is_alive():
                time.sleep(wevis.SSLEEP_LAUNCH)
        finally:
            self.stop()
        if self._exception:
            raise self._exception

    @property
    def log(self):
        """ Provides public access to this Manager's ``logging.Logger``. """
        return self._log

    def run(self):
        """ See: ``threading.Thread.run``. """
        if self._status != Server.PRE_RUN:
            raise Exception('Already started')

        self._log.info('Server starting...')

        self._status = Server.RUNNING
        self._halt.clear()
        self._manager.start()
        self._listener.start()
        self._room.start()
        while not self._halt.is_set():
            time.sleep(wevis.SSLEEP_SERVER)

        # Check if everything is shutting down here. Then delete the objects
        if self._listener.is_alive():
            self._log.info('Waiting for listener to shut down')
            while self._listener.is_alive():
                time.sleep(wevis.SSLEEP_SHUTDOWN)
            del(self._listener)
        if self._manager.is_alive():
            self._log.info('Waiting for manager to shut down')
            while self._manager.is_alive():
                time.sleep(wevis.SSLEEP_SHUTDOWN)
            del(self._manager)
        if self._room.is_alive():
            self._log.info('Waiting for room to shut down')
            while self._room.is_alive():
                time.sleep(wevis.SSLEEP_SHUTDOWN)
            del(self._room)

        # Close socket
        self._sock.close()

        # Post-running state!
        self._status = Server.POST_RUN

        # Log exception, if any
        if self._exception:
            try:
                raise self._exception
            except Exception:
                self._log.critical(
                    'Server halted with exception', exc_info=True)
        else:
            self._log.info('Server halted.')

    @property
    def room(self):
        """ Returns this server's only room. """
        # TODO: Allow multiple rooms
        return self._room

    @property
    def socket(self):
        """ Returns this server's socket. """
        return self._sock

    def stop(self, exception=None):
        """
        Stops this server.

        If an exception is passed in, this is stored as the reason for halting.

        Called without an exception, this is equivalent to
        ``server.halt_event.set()``.
        """
        if exception is not None:
            self._exception = exception
        self._halt.set()


class Listener(threading.Thread):
    """
    Listens for incoming connections.

    Arguments:

    ``server``
        The server to listen for.
    ``manager``
        The manager to pass new connections to.
    ``name``
        A name to use for the Listener's thread and logger.

    """

    def __init__(self, server, manager, name='wevis.listener'):
        super().__init__(name=name)

        # Logging
        self._log = logging.getLogger(name)
        if wevis._LOGGING_LEVEL is not None:
            self._log.setLevel(wevis._LOGGING_LEVEL)

        # Arguments
        self._server = server
        self._manager = manager

        # Run as background process
        self.setDaemon(True)

    @property
    def log(self):
        """ Provides public access to this Listener's ``logging.Logger``. """
        return self._log

    def run(self):
        """ See: ``threading.Thread.run``. """
        self._log.info('Listener starting...')

        try:
            self._server.socket.listen()

            # Accept any new connections
            while not self._server.halt_event.is_set():
                try:
                    # Establish connection (blocking call)
                    conn, addr = self._server.socket.accept()

                    # Pass new connection to manager
                    self._manager.add(conn, addr)
                except socket.error:
                    time.sleep(wevis.SSLEEP_LISTENER)

        except Exception as e:
            self._server.stop(e)

        self._log.info('Listener stopped')


class Manager(threading.Thread):
    """
    Manages active connections, sending and receiving messages.

    Arguments:

    ``server``
        The sever to handle connections for
    ``name``
        A name to use for the Manager's thread and logger.

    """

    def __init__(self, server, name='wevis.manager'):
        super().__init__(name=name)

        # Logging
        self._log = logging.getLogger(name)
        if wevis._LOGGING_LEVEL is not None:
            self._log.setLevel(wevis._LOGGING_LEVEL)

        # Arguments
        self._server = server

        # Run as daemon process
        self.setDaemon(True)

        # Active connections
        self._connections = []

        # Number of activate connections per user
        self._user_counts = {}

        # Incoming connections, as tuples ``(socket, address)``.
        self._incoming = queue.Queue()

    def add(self, connection, address):
        """ Adds a new connection to this manager. """
        self._incoming.put(Connection(self, connection, address))

    @property
    def log(self):
        """ Provides public access to this Manager's ``logging.Logger``. """
        return self._log

    def run(self):
        """ See: ``threading.Thread.run``. """
        self._log.info('Manager starting...')

        try:
            while not self._server.halt_event.is_set():

                changed = False

                # Scan for closed connections
                closed = []
                for c in self._connections:
                    if not c.alive:
                        closed.append(c)
                if closed:
                    changed = True
                    self._log.info(
                        f'Removing {len(closed)} closed connection(s).')
                for c in closed:
                    c.close()
                    self._connections.remove(c)
                del(closed)

                # Add incoming connections
                while not self._incoming.empty():
                    # Note: This could fail if some other thread also empties
                    # the same list.
                    changed = True
                    self._log.info('Accepting incoming connection')
                    self._connections.append(self._incoming.get_nowait())

                # Show updated connection count
                if changed:
                    self._log.info(
                        f'Open connections: {len(self._connections)}')

                # Maintain open connections
                for c in self._connections:
                    c.tick()

                # Sleep
                time.sleep(wevis.SSLEEP_MANAGER)

        except Exception as e:
            self._server.stop(e)

        self._log.info('Manager stopped')

    @property
    def server(self):
        """ This manager's server. """
        return self._server

    def user_count(self, user):
        """
        Returns the number of active connections for the given ``user``.
        """
        return self._user_counts.get(user.name, 0)

    def user_enter(self, connection):
        """ Called when a user connects. """
        # Update connection count
        try:
            self._user_counts[connection.user.name] += 1
        except KeyError:
            self._user_counts[connection.user.name] = 1
        self._log.debug(
            f'User {connection.user.name} has'
            f' {self._user_counts[connection.user.name]} active connections.')

        # Notify room
        self.server.room.user_enter(connection)

    def user_exit(self, user):
        """ Called when a user disconnects. """
        # Update connection count
        self._user_counts[user.name] -= 1
        self._log.debug(
            f'User {user.name} has {self._user_counts[user.name]} active'
            ' connections.')

        # Notify room
        self.server.room.user_exit(user)


class Connection(object):
    """
    Represents a server-side connection with a client.

    Arguments:

    ``manager``
        The manager managing this connection.
    ``conn``
        The socket connection that this ``Connection`` is based on.
    ``addr``
        The ip address for this connection.

    """
    def __init__(self, manager, conn, addr):

        # Manager
        self._manager = manager

        # Socket connection
        self._conn = conn
        self._conn.setblocking(False)

        # Remote IP address
        self._addr = addr

        self._salt = None   # Salt generated and sent to user for login
        self._user = None   # User object

        # Time out
        self._ping_time = None
        self._ping_sent = False

        # Outgoing messages
        self._outgoing = queue.Queue()

        # Message IO
        self._reader = wevis.MessageReader(self._conn)
        self._writer = wevis.MessageWriter(self._conn)

        # Flag to show this connection is alove
        self._alive = True

    @property
    def alive(self):
        """ Returns ``True`` iff this connection is still alive. """
        return self._alive

    def close(self, reason=None):
        """
        Closes this connection. A reason for closing can be given to use in the
        log.

        This method always returns ``False``, so that it can be used as e.g.
        ``return self.close('Something went wrong')``.
        """
        if self._alive:
            if self._user:
                self._manager.user_exit(self._user)

            if reason:
                self._manager.log.info(f'Closing connection: {reason}')
            else:
                self._manager.log.info('Closing connection.')

            try:
                self._conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                self._conn.close()

            self._alive = False
            self._user = None

        return False

    def queue(self, message):
        """ Queues a message to send to the client. """
        self._outgoing.put(message)

    def q(self, _name, **_values):
        """
        Short-hand for ``queue(wevis.Message(name, **values))``.

        See :meth:`queue` and :class:`Message`.
        """
        self._outgoing.put(wevis.Message(_name, **_values))

    def tick(self):
        """
        Called by the manager every time the Connection gets some time to work.
        """
        if not self._alive:
            return

        if self._user:
            self.tick_normal()
        elif self._salt:
            self.tick_login()
        else:
            self.tick_initial()

    def tick_initial(self):
        """ First contact with the client: Send salt and welcome. """

        # Create salt
        self._salt = wevis.encrypt(
            f'where-is-{random.random()}',
            f'{random.random()}-ben-nevis')

        # Create and send ready message
        self._manager.log.debug('Sending welcome message')
        self._writer.send_blocking(wevis.Message('_welcome', salt=self._salt))

        # Set time-out for login
        self._ping_time = time.time() + wevis.LOGIN_TIMEOUT

    def tick_login(self):
        """ Login process. """

        # Wait for a message
        try:
            message = self._reader.read()
        except Exception as e:
            return self.close(str(e))

        if message:
            # Check if correct message received
            if message.name != '_login':
                self._writer.send_blocking(wevis.Message(
                    '_loginReject', reason='Unexpected message.'))
                return self.close('Rejected login: unexpected message.')

            # Validate user version
            version = (message.get('major'), message.get('minor'),
                       message.get('revision'))
            if not self._manager.server._version_validator(*version):
                self._writer.send_blocking(wevis.Message(
                    '_loginReject', reason='Client requires update.'))
                return self.close('Rejected login: client requires update.')

            # Validate login credentials
            user = self._manager.server._user_validator(
                message.get('username'), message.get('password'), self._salt)
            if not user:
                self._writer.send_blocking(wevis.Message(
                    '_loginReject', reason='Invalid credentials.'))
                return self.close('Rejected login: invalid credentials.')

            # Validate user count: Do this after password validation so that we
            # don't give out info on whether users are logged in or not.
            count = self._manager.user_count(user)
            if count >= wevis.MAX_CONNECTIONS_PER_USER:
                self._writer.send_blocking(wevis.Message(
                    '_loginReject',
                    reason='Maximum number of connections per user reached.'))
                return self.close(
                    'Rejected login: maximum number of connections per user'
                    ' reached.')

            # Accept
            self._manager.log.debug(f'Accepted login from {user}.')
            self._writer.send_blocking(wevis.Message('_loginAccept'))
            self._user = user
            self._manager.user_enter(self)

        # Login must happen within x seconds
        elif time.time() > self._ping_time:
            return self.close('Login time out')

    def tick_normal(self):
        """ Normal mode of operation. """

        # Send outgoing messages
        for i in range(self._outgoing.qsize()):
            self._writer.queue(self._outgoing.get(block=False))
        self._writer.send()

        # Parse incoming messages
        message = None
        try:
            message = self._reader.read()
        except Exception as e:
            return self.close(str(e))

        while message:
            if message.name == '_pong':
                self._manager.log.debug(f'Pong from {self._user.name}')
                self._ping_sent = False
                self._ping_time = time.time() + wevis.PING_INTERVAL
            else:
                self._manager.log.debug(
                    f'Received message {message} from {self._user.name}')
                # Send message to its destination
                # TODO: Allow multiple rooms etc.
                self._manager.server.room.send(self, message)

            # Read next message
            try:
                message = self._reader.read()
            except Exception as e:
                return self.close(str(e))

        # Check connection status
        if time.time() > self._ping_time:
            if self._ping_sent:
                return self.close('Ping time out')
            else:
                self._manager.log.debug(f'Pinged {self._user.name}')
                self.q('_ping')
                self._ping_sent = True
                self._ping_time = time.time() + wevis.PING_TIMEOUT

    @property
    def user(self):
        """ The current user (only when logged in). """
        return self._user


class Room(threading.Thread):
    """
    Abstract class that handles messages received through connections.

    Typical implementations overwrite only the ``handle`` method.

    A name for the Room's ``threading.Thread`` and ``logging.Logger`` can be
    specified with the constructor argument ``name``.
    """

    def __init__(self, name='wevis.room'):
        super().__init__(name=name)

        # Logging
        self._log = logging.getLogger(name)
        if wevis._LOGGING_LEVEL is not None:
            self._log.setLevel(wevis._LOGGING_LEVEL)

        # Run as daemon process
        self.setDaemon(True)

        # Incoming messages, as tuples (connection, message)
        self._incoming = queue.Queue()

    def handle(self, connection, message):
        """
        Overwrite this to handle messages from users.

        The user sending the message can be obtained from ``connection.user``.
        Replies can be sent with :meth:`connection.queue()`.
        """
        pass

    @property
    def log(self):
        """ Provides public access to this Room's ``logging.Logger``. """
        return self._log

    def run(self):
        """ See: ``threading.Thread.run``. """
        self._log.info('Room starting...')

        # Check for server
        if self._server is None:
            raise ValueError('Room cannot be run before server is set.')

        # Handle incomming messages
        try:
            while not self._server.halt_event.is_set():
                while not self._incoming.empty():
                    connection, message = self._incoming.get_nowait()

                    try:
                        self.handle(connection, message)
                    except Exception:
                        self._log.error(
                            f'Error handling message from {connection.user}.',
                            exc_info=True)

                # Sleep
                time.sleep(wevis.SSLEEP_ROOM)

        except Exception as e:
            self._server.stop(e)

        self._log.info('Room stopped')

    def send(self, connection, message):
        """ Sends a message to this room. """
        self._incoming.put((connection, message))

    def set_server(self, server):
        """ Passes a server instance to this room. """
        if not isinstance(server, Server):
            raise ValueError('Server must be a wevis.Server.')
        self._server = server

    def user_enter(self, connection):
        """
        This function is called whenever a user enters this room; overwrite it
        to e.g. send welcome messages.
        """
        pass

    def user_exit(self, connection):
        """
        This function is called whenever a user leaves this room.

        It can be overwritten for e.g. user management, but the ``connection``
        may no longer be open at this point, so sending messages is not
        advised.
        """
        pass


class User(object):
    """
    A server user.

    Server-side code built on ``wevis`` can override this class and add in
    extra properties. These will be available for a ``Room`` when a connection
    is passed in (through ``connection.user``).

    Arguments

    ``username``
        The username to connect with.

    """
    def __init__(self, username):
        super().__init__()
        self._username = username

    @property
    def name(self):
        return self._username

    def __str__(self):
        return str(self._username)
