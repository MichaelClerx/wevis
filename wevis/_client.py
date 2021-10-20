#!/usr/bin/env python3
"""
Client-side code for wevis.

Example usage in an asynchronous application::

    c = wevis.Client(version=(1, 2, 3), username='michael', password='michael')
    c.start()
    try:
        while c.is_alive():
            msg = c.receive()
            if msg:
                reply = do_things_with_message(msg)
                c.queue(reply)
            time.sleep(0.1)
    finally:
        c.stop()

Example usage in a sequential application::

    c = wevis.Client(version=(1, 2, 3), username='michael', password='michael')
    c.start()

    try:
        for i in range(100):
            out = make_some_message()
            c.queue(out)
            msg = c.receive_blocking()
            do_something_with_reply(msg)

    except SocketClosedError:
        raise Exception('Connection closed unexpectedly.')
    finally:
        c.stop()


"""
import logging
import queue
import socket
import threading
import time

import wevis


class ClientError(Exception):
    """
    Raised when an error occurs while running the client.
    """
    pass


class ConnectionError(ClientError):
    """
    Raised when the client tries to connect but fails.
    """
    pass


class UnexpectedMessageError(ClientError):
    """
    Raised when an unexpected message is received.

    Arguments:

    ``expected``
        A string with the expected message type
    ``got``
        The actual message received
    """
    def __init__(self, expected, got):
        super(UnexpectedMessageError, self).__init__(
            f'Expected {expected} got {got.name}.')


class Client(threading.Thread):
    """
    A client that can connect to the server.

    Arguments

    ``version``
        The client version, as a tuple of integers ``major, minor, revision``.
    ``username``
        The username to connect with.
    ``password``
        The user's password.
    ``host``
        The hostname this server is running on (or ``None`` to autodetect).
    ``port``
        The port to listen on (or ``None`` for the default).
    ``name``
        A name for this client's ``threading.Thread`` and ``logging.Logger``.

    """
    PRE_RUN = 0
    PRE_CONNECT = 1
    CONNECTED = 2
    POST_RUN = 4

    def __init__(self, version, username, password,
                 host=None, port=None, name='wevis.client'):
        super(Client, self).__init__(name=name)

        # Status
        self._status = Client.PRE_RUN

        # Logger
        self._log = logging.getLogger(name)
        if wevis.logging_level is not None:
            self._log.setLevel(wevis.logging_level)
        self._log.info('Creating client')

        # Version
        if len(version) != 3:
            raise ValueError('Version must be three integers.')
        self._version = [int(x) for x in version]
        del(version)

        # User credentials
        self._username = username
        self._password = password

        # Host and port
        self._host = host if host else socket.gethostname()
        self._port = port if port else wevis.default_port
        del(host, port)

        # Socket
        self._conn = None

        # Message streams
        self._reader = None
        self._writer = None

        # Run as background process
        self.setDaemon(True)

        # Event to halt the client
        self._halt = threading.Event()

        # Incoming messages
        self._incoming = queue.Queue()

        # Outgoing messages
        self._outgoing = queue.Queue()

        # Exception during run
        self._exception = None

    def close(self, reason=None):
        """
        Closes this connection. A reason for closing can be given to use in the
        log.
        """
        if self._conn is None:
            return

        if reason:
            self._log.info(f'Closing connection: {reason}')
        else:
            self._log.info('Closing connection.')

        try:
            self._conn.close()
        except Exception as e:
            self._exception = e
            self._log.error('Exception when closing connection', exc_info=True)

        self._conn = None

    def _connect(self):
        """ Connects to the server. """
        if self._conn:
            raise RuntimeError('Already connected.')

        # Create socket connection
        self._log.debug('Creating socket')
        self._conn = socket.socket()
        self._conn.connect((self._host, self._port))
        self._conn.setblocking(False)

        # Create message reader and writer
        self._log.debug('Creating message I/O')
        self._reader = wevis.MessageReader(self._conn)
        self._writer = wevis.MessageWriter(self._conn)

        # Send login credentials
        self._log.debug('Receiving first data')
        ready = self._receive_blocking('_welcome')
        self._log.debug('Welcome received')

        self._writer.send_blocking(wevis.Message(
            '_login',
            username=self._username,
            password=wevis.encrypt(self._password, ready.get('salt')),
            major=self._version[0],
            minor=self._version[1],
            revision=self._version[2],
        ))

        # Check result
        result = self._receive_blocking('_loginAccept', '_loginReject')
        if result.name == '_loginReject':
            self.close()
            raise ConnectionError(f'Login rejected: {result.get("reason")}')

    def receive(self):
        """
        Returns a new message sent from the server, or ``None`` if none is
        available.
        """
        try:
            return self._incoming.get_nowait()
        except queue.Empty:
            return None

    def receive_blocking(self, *expected):
        """
        Waits for and then returns a new message sent from the server.

        If only certain types of message are expected, they can be specified
        as extra arguments. In this case, any other messages will trigger an
        :class:`UnexpectedMessageError`.
        """
        # Note: This method is for use by other threads
        message = None
        while message is None and not self._halt.is_set():
            message = self.receive()
            if message is None:
                time.sleep(0.01)
        if message is None:
            # Halt set: discard message
            raise ClientError('Client shut down while waiting for message.')
        if expected and message.name not in expected:
            raise UnexpectedMessageError(expected, message)
        return message

    def _receive_blocking(self, *expected):
        """
        Receives a message (blocking). For internal use only (breaks pinging
        etc.).

        If only certain types of message are expected, they can be specified
        as extra arguments. In this case, any other messages will trigger an
        :class:`UnexpectedMessageError`.
        """
        message = self._reader.read_blocking()
        self._log.debug(f'Received message: {message}')

        if expected and message.name not in expected:
            raise UnexpectedMessageError(expected, message)
        return message

    def run(self):
        """ Runs the client thread. """
        self._log.info('Starting client...')
        self._status = Client.PRE_CONNECT

        # Connect
        self._log.info('Attempting to connect')
        try:
            self._connect()
        except Exception as e:
            self._log.error('Unable to connect', exc_info=True)
            self._status = Client.POST_RUN
            self._exception = e
            return

        self._status = Client.CONNECTED
        self._log.info('Login complete.')

        try:
            # Do stuff until told to stop
            while not self._halt.is_set():

                # Send outgoing messages
                for i in range(self._outgoing.qsize()):
                    self._writer.queue(self._outgoing.get(block=False))
                self._writer.send()

                # Parse incoming messages
                message = self._reader.read()
                while message:
                    if message.name == '_ping':
                        self._log.debug('Ping!')
                        self.q('_pong')
                    else:
                        self._log.debug(f'Received message {message}')
                        self._incoming.put(message)

                    # Read next message
                    message = self._reader.read()

                time.sleep(0.01)
        except Exception as e:
            self._log.error('Error during client run', exc_info=True)
            self._exception = e
        finally:
            self.close()
            self.stop()
            self._status = Client.POST_RUN
            self._log.info('Client stopped')

    def queue(self, message):
        """ Queues a message to send to the server. """
        self._outgoing.put(message)

    def q(self, _name, **_values):
        """
        Short-hand for ``queue(wevis.Message(_name, **_values))``.

        See :meth:`queue` and :class:`Message`.
        """
        self._outgoing.put(wevis.Message(_name, **_values))

    def start_blocking(self):
        """
        Starts this thread and waits for it to be up and running.
        """
        # Note: This method is for use by other threads
        self.start()
        while self._status in (Client.PRE_RUN, Client.PRE_CONNECT):
            time.sleep(0.1)
        if self._exception:
            raise ClientError('Unable to start client') from self._exception

    def stop(self):
        """ Stops this client thread. """
        self._halt.set()

