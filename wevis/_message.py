#!/usr/bin/env python3
"""
Messages sent between clients and servers.
"""
import errno
import socket
import struct
import time


class SocketClosedError(Exception):
    """
    Raised if a socket is closed while a message is being read.
    """
    pass


class MessageDefinition(object):
    """
    Defines a message.

    Statically, this class acts as a registry of available messages.
    """

    # Static variables
    _messages = {}
    _ids = {}
    _last_id = 0
    TYPES = {int: 'i', float: 'd', str: 's', bytes: 'b'}

    def __init__(self, _name, **_arguments):
        """
        Registers a new message with the name ``_name`` and any arguments
        given as ``name=type`` keyword arguments.

        Notes:
        - Message definitions are immutable objects.
        - The constructor argument names start with an underscore so that e.g.
          "name" can still be used for a message argument.
        """

        # Make sure that the message is not already defined
        if _name in self._messages:
            raise AttributeError(f'Message "{_name}" already defined.')

        # Private variables
        self._id = None         # Unique id for this definition
        self._name = _name      # This message's name
        self._arguments = {}    # Ordered list with attributes

        # Assign a unique ID
        MessageDefinition._last_id += 1
        self._id = MessageDefinition._last_id

        # Store the arguments and argument types in alphabetical order
        self._arguments = {}

        # Create the packing code for this message's fixed-size part and
        # calculate its size. Use the field ``_vectors`` to store tuples
        # (index, type) with the index and type of variable size arguments.
        self._pack_code = [b'<']
        self._pack_size = 0
        self._vectors = []
        i = 0
        for name, kind in sorted(_arguments.items(), key=lambda x: x[0]):
            if kind == int:
                self._pack_code.append(b'i')
                self._pack_size += 4
            elif kind == float:
                self._pack_code.append(b'd')
                self._pack_size += 8
            elif kind == str:
                self._pack_code.append(b'i')
                self._pack_size += 4
                self._vectors.append((i, str))
            elif kind == bytes:
                self._pack_code.append(b'i')
                self._pack_size += 4
                self._vectors.append((i, bytes))
            else:
                raise AttributeError('Unknown argument type <' + kind + '>.')
            i += 1
            self._arguments[name] = kind
        self._pack_code = b''.join(self._pack_code)

        # Register this message definition
        MessageDefinition._messages[self._name] = self
        MessageDefinition._ids[self._id] = self

    def arguments(self):
        """
        Returns an iterator over this definition's ``(name, type)`` pairs.
        """
        return self._arguments.items()

    #@staticmethod
    #def exists(name):
    #    """ Checks if a message with given ``name`` is defined. """
    #    return name in MessageDefinition._messages

    #@staticmethod
    #def id_exists(id):
    #    """ Checks if a message with the given ``id`` is defined. """
    #    return id in MessageDefinition._ids

    @staticmethod
    def fetch(name):
        """ Fetches the message definition with the given ``name``. """
        return MessageDefinition._messages[name]

    #@staticmethod
    #def fetch_by_id(cid):
    #    return MessageDefinition._ids[cid]

    def get_argument_type(self, name):
        """
        Returns the data type required for the argument specified by ``name``.
        """
        return self._arguments[name]

    def __hash__(self):
        """ Returns a hash for this message definition. """
        return hash(self._id)

    @property
    def id(self):
        """ Returns this message definition's id. """
        return self._id

    @property
    def name(self):
        """ Returns this message definition's name. """
        return self._name

    def pack(self, message):
        """ Packs a message into binary form for network transmission. """

        # Pack message id
        b = struct.pack(b'<i', self._id)

        # Fixed length arguments and variable length argument sizes
        fixed = []
        for name in self._arguments:
            fixed.append(message.get(name))

        # Create vector packing string and add lengths to list of fixed args
        vectors = []
        vector_code = [b'<']
        for i, kind in self._vectors:

            # Get value, length of value
            if kind == str:
                v = fixed[i].encode('utf-8')
            elif kind == bytes:
                v = fixed[i]
            else:
                raise Exception(f'Unknown vector variable type {kind}.')
            n = len(v)

            # Replace value in fixed list with length of value
            fixed[i] = n

            # Add value to list of vector data
            vectors.append(v)

            # Add packing code to list of vector packing codes
            vector_code.append(str(n).encode('utf-8'))
            if kind in (str, bytes):
                vector_code.append(b's')

        # Pack fixed size arguments
        b += struct.pack(self._pack_code, *fixed)

        # Pack variable size arguments
        if vectors:
            b += struct.pack(b''.join(vector_code), *vectors)

        return b

    @staticmethod
    def unpack(data):
        """ Unpacks a binary coded message. """
        # Fetch the message definition
        cid = struct.unpack(b'<i', data[0:4])[0]
        definition = MessageDefinition._ids[cid]

        # Create an empty message
        message = Message(definition)

        # Unpack fixed length arguments (and lengths of variable sized args)
        code, size = definition._pack_code, definition._pack_size
        fixed = struct.unpack(code, data[4:4 + size])

        # Unpack variable size arguments
        vectors = None
        if definition._vectors:
            code = [b'<']
            for i, kind in definition._vectors:
                code.append(str(fixed[i]).encode('utf-8'))
                if kind in (str, bytes):
                    code.append(b's')
                else:
                    raise Exception(f'Unknown data type {kind}.')
            code = b''.join(code)
            vectors = struct.unpack(code, data[4 + size:])

        # Set arguments in message
        args = {}
        fixed = iter(fixed)
        if vectors:
            vectors = iter(vectors)
        for name, kind in definition._arguments.items():
            if kind == str:
                args[name] = next(vectors).decode('utf-8')
            elif kind == bytes:
                args[name] = next(vectors)
            else:
                args[name] = next(fixed)
        message.set(**args)

        # Return unpacked arguments
        return message

    @staticmethod
    def setup():
        """ Registers built-in and custom messages. """
        if MessageDefinition._initialized:
            raise Exception("Message definitions are already initialized")


class Message(object):

    def __init__(self, _name, **_values):
        """
        Creates a message of the type specified by ``_name``, where ``_name``
        can be either a name (string) or a :class:`MessageDefinition`.

        Initial arguments can be set using keyword arguments, for example
        ``c = Message('ready', major=2)``.
        """

        # Set properties
        if type(_name) != MessageDefinition:
            _name = MessageDefinition.fetch(_name)
        self._definition = _name

        # Message arguments
        self._argument_values = {}

        # Set the initial values for the arguments
        for name, kind in self._definition.arguments():
            self._argument_values[name] = _values.get(name, None)

    @property
    def definition(self):
        return self._definition

    def get(self, *name):
        """
        Returns one or multiple arguments.

            message.get('x') --> x
            message.get('x', 'y') --> (x, y)

        """
        if len(name) == 1:
            return self._argument_values[name[0]]
        return (self._argument_values[x] for x in name)

    @property
    def name(self):
        """ Returns this message's name. """
        return self._definition.name

    def pack(self):
        """ Packs this message into a binary form for network transmission. """
        return self._definition.pack(self)

    def set(self, **kwargs):
        """
        Sets one or more message properties using keyword arguments.

        For example::

            c.set(major=1, minor=2)

        """
        for name, value in kwargs.items():
            kind = self._definition.get_argument_type(name)
            self._argument_values[name] = kind(value)

    def __str__(self):
        s = [f'Message<{self._definition.id}:{self._definition.name}>']
        if self._argument_values:
            s.append('(')
            s.append(', '.join([
                f'{k}={v}' for k, v in self._argument_values.items()]))
            s.append(')')
        return ''.join(s)

    @staticmethod
    def unpack(data):
        """
        Unpacks a message.
        """
        return MessageDefinition.unpack(data)


class MessageReader(object):
    """
    Reads messages from a socket.

    Arguments:

    ``connection``
        The socket connection to read from.

    """
    def __init__(self, connection):
        self._conn = connection
        self._read = 0
        self._size = None
        self._buff = b''

    def read(self):
        """ Returns a :class:`Message` if one is available, else ``None``. """
        if not self._size:
            # Read message size
            try:
                self._buff += self._conn.recv(4 - self._read)
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    return None
                raise e
            self._read = len(self._buff)
            if self._read == 0:
                raise SocketClosedError('Socket closed unexpectedly.')
            if self._read == 4:
                self._size = struct.unpack(b'<i', self._buff)[0]
                self._buff = b''
                self._read = 0
        # New if statement, because size may now be set.
        if self._size:
            # Read message
            try:
                self._buff += self._conn.recv(self._size - self._read)
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    return None
                raise e
            self._read = len(self._buff)
            if self._read == 0:
                raise SocketClosedError('Socket closed unexpectedly.')
            if self._read == self._size:
                message = MessageDefinition.unpack(self._buff)
                self._size = None
                self._buff = b''
                self._read = 0
                return message
        return None

    def read_blocking(self, timeout=None):
        """
        Like :meth:`read` but blocks until a message is available.
        """
        message = self.read()

        if timeout:
            tmax = time.time() + float(timeout)
            while (not message) and (time.time() < tmax):
                time.sleep(0.5)
                message = self.read()
        else:
            while not message:
                time.sleep(0.5)
                message = self.read()
        return message


class MessageWriter(object):
    """
    Writes messages to a socket.

    Arguments:

    ``connection``
        The socket connection to write to.

    """
    def __init__(self, connection):
        self._conn = connection
        self._buff = b''

    def send_blocking(self, message):
        """ Sends a message immediately, blocks until done. """
        b = message.pack()
        b = struct.pack(b'<i', len(b)) + b
        size = len(b)
        n = 0
        while n < size:
            try:
                n += self._conn.send(b[n:])
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    time.sleep(0.5)
                else:
                    raise e

    def queue(self, message):
        """ Queues a message for later transmission. """
        b = message.pack()
        self._buff += struct.pack(b'<i', len(b)) + b

    def send(self):
        """ Sends any waiting data. """
        while self._buff:
            try:
                n = self._conn.send(self._buff)
                self._buff = self._buff[n:]
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    return
                raise e


class DefinitionList(object):
    """
    Represents a list of message definitions.

    New definitions can be added with :meth:`add`, but creation of
    :class:`MessageDefinition` objects is delayed until :meth:`instantiate` is
    called.

    """
    def __init__(self):
        self._definitions = {}

    def add(self, _name, **_arguments):
        """
        Adds a definition to the list.
        """

        if _name in self._definitions:
            raise ValueError(f'Duplicate definition {_name}.')
        self._definitions[_name] = _arguments

    def instantiate(self):
        """
        Instantiates all message definitions in the list, and clears the list.
        """
        for name, arguments in self._definitions.items():
            MessageDefinition(name, **arguments)
        self._definitions = {}

    @staticmethod
    def load(path):
        """
        Loads definitions from a file.
        """
        raise NotImplementedError('todo')

