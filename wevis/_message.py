#!/usr/bin/env python3
"""
Messages sent between clients and servers.
"""
import errno
import re
import socket
import struct
import time

import wevis

# Message name regex
NAME = re.compile(r'^[a-zA-Z_]\w*$')
ARGS = re.compile(r'^[a-zA-Z]\w*$')


class SocketClosedError(Exception):
    """
    Raised if a socket is closed while a message is being read.
    """
    pass


class MessageDefinition(object):
    """
    Defines a message.

    Creating a new ``MessageDefinition`` registers a message type with the name
    ``name`` and arguments given by keyword arguments ``arg_name=type``.
    Server and client need to use agreed upon message definitions.

    Supported argument types are

    - ``int``, a 4 byte signed integer.
    - ``float``, an 8 byte float.
    - ``str``,  a variable-length unicode string.
    - ``bytes``, a variable-length bytes string.
    - ``'?f'``, a variable-length array of 4 byte floats.
    - ``'?d'``, a variable-length array of 8 byte floats.

    """

    # Static variables
    _names = {}
    _ids = {}
    _last_id = 0

    def __init__(self, _name, **_arguments):
        # Notes:
        # - Message definitions are immutable objects.
        # - The constructor argument names start with an underscore so that
        #   "name" and "arguments" can still be used as message argument names.

        # Make sure that the name is OK
        if NAME.match(_name) is None:
            raise ValueError(
                'Message name must start with letter and consist only of'
                f' letters, numbers, or underscores. Got "{_name}".')

        # Make sure that the message is not already defined
        if _name in self._names:
            raise ValueError(f'Message "{_name}" already defined.')

        # Private variables
        self._id = None         # Unique id for this definition
        self._name = _name      # This message's name
        self._arguments = {}    # Ordered list with attributes

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
            if ARGS.match(name) is None:
                raise ValueError(
                    'Message argument name must start with letter and consist'
                    ' only of letters, numbers, or underscores.')
            if kind == int:
                self._pack_code.append(b'i')
                self._pack_size += 4
            elif kind == float:
                self._pack_code.append(b'd')
                self._pack_size += 8
            elif kind in (str, bytes, '?f', '?d'):
                # Unsigned int for size
                self._pack_code.append(b'I')
                self._pack_size += 4
                self._vectors.append((i, kind))
            else:
                raise ValueError('Unknown argument type <' + kind + '>.')
            i += 1
            self._arguments[name] = kind
        self._pack_code = b''.join(self._pack_code)

        # Assign a unique ID
        MessageDefinition._last_id += 1
        self._id = MessageDefinition._last_id

        # Register this message definition
        MessageDefinition._names[self._name] = self
        MessageDefinition._ids[self._id] = self

    def arguments(self):
        """
        Returns an iterator over this definition's ``(name, type)`` pairs.
        """
        return self._arguments.items()

    def argument_type(self, name):
        """
        Returns the data type required for the argument specified by ``name``.
        """
        return self._arguments[name]

    @staticmethod
    def fetch(name):
        """ Fetches the message definition with the given ``name``. """
        return MessageDefinition._names[name]

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
        b = struct.pack(b'<I', self._id)

        # Fixed length arguments and variable length argument sizes
        fixed = []
        for name in self._arguments:
            fixed.append(message.get(name))

        # Create vector packing string and add lengths to list of fixed args
        vector_code = [b'<']
        vector_data = []
        for i, kind in self._vectors:

            # Get value, length of value
            v = fixed[i]
            n = len(v)

            # Replace value in fixed list with length of value
            fixed[i] = n

            # Add value (string) or values (list) to list of vector data
            if kind == str:
                vector_data.append(v.encode('utf-8'))
            elif kind == bytes:
                vector_data.append(v)
            else:
                vector_data.extend(v)

            # Add packing code to list of vector packing codes
            vector_code.append(str(n).encode('utf-8'))
            if kind in (str, bytes):
                vector_code.append(b's')
            elif kind == '?f':
                vector_code.append(b'f')
            elif kind == '?d':
                vector_code.append(b'd')
            else:
                raise Exception(f'Unknown vector variable type {kind}.')

        # Pack fixed size arguments
        b += struct.pack(self._pack_code, *fixed)

        # Pack variable size arguments
        if vector_data:
            b += struct.pack(b''.join(vector_code), *vector_data)

        return b

    @staticmethod
    def unpack(data):
        """ Unpacks a binary coded message. """

        # Fetch the message definition
        cid = struct.unpack(b'<I', data[0:4])[0]
        definition = MessageDefinition._ids[cid]

        # Create an empty message
        message = Message(definition)

        # Unpack fixed length arguments (and lengths of variable sized args)
        code, size = definition._pack_code, definition._pack_size
        fixed = struct.unpack(code, data[4:4 + size])

        # Unpack variable size arguments
        vector_data = None
        if definition._vectors:
            vector_code = [b'<']
            for i, kind in definition._vectors:
                # Add vector size
                vector_code.append(str(fixed[i]).encode('utf-8'))
                # Add vector contents type
                if kind in (str, bytes):
                    vector_code.append(b's')
                elif kind == '?f':
                    vector_code.append(b'f')
                elif kind == '?d':
                    vector_code.append(b'd')
                else:
                    raise Exception(f'Unknown vector data type {kind}.')
            vector_code = b''.join(vector_code)
            vector_data = struct.unpack(vector_code, data[4 + size:])

        # Set arguments in message
        args = {}
        fixed = iter(fixed)
        ivector = 0
        try:
            for name, kind in definition._arguments.items():
                v = next(fixed)
                if kind == str:
                    args[name] = vector_data[ivector].decode('utf-8')
                    ivector += 1
                elif kind == bytes:
                    args[name] = vector_data[ivector]
                    ivector += 1
                elif kind in ('?d', '?f'):
                    args[name] = vector_data[ivector:ivector + v]
                    ivector += v
                else:
                    args[name] = v
        except StopIteration:
            raise Exception(
                'Unexpected StopIteration when unpacking {message.name}.')
        message.set(**args)

        # Return unpacked arguments
        return message

    @staticmethod
    def setup():
        """ Registers built-in and custom messages. """
        if MessageDefinition._initialized:
            raise Exception('Message definitions are already initialized')


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
            kind = self._definition.argument_type(name)
            if kind in ('?f', '?d'):
                self._argument_values[name] = [float(x) for x in value]
            else:
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
                raise
            self._read = len(self._buff)
            if self._read == 0:
                raise SocketClosedError('Socket closed unexpectedly.')
            if self._read == 4:
                self._size = struct.unpack(b'<I', self._buff)[0]
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
                raise
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

    def _read_blocking_internal(self, timeout=None):
        """
        Like :meth:`read` but blocks until a message is available.

        Should be used with care, e.g. only during login.
        """
        message = self.read()

        if timeout:
            tmax = time.time() + float(timeout)
            while (not message) and (time.time() < tmax):
                time.sleep(wevis.SLEEP_READ_BLOCKING_INTERNAL)
                message = self.read()
        else:
            while not message:
                time.sleep(wevis.SLEEP_READ_BLOCKING_INTERNAL)
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
    def from_file(path):
        """
        Loads definitions from a file.
        """
        types = {
            'int': int,
            'float': float,
            'str': str,
            'bytes': bytes,
            '?f': '?f',
            '?d': '?d',
        }

        defs = DefinitionList()
        with open(path, 'r') as f:
            for line in f:

                # Allow comments
                try:
                    line = line[:line.index('#')]
                except ValueError:
                    pass

                # Skip empty lines
                line = line.strip()
                if not line:
                    continue

                # Parse line
                parts = [x.strip() for x in line.split()]
                name = parts[0]
                args = {}
                for part in parts[1:]:
                    try:
                        n, t = [x.strip() for x in part.split('=')]
                    except ValueError:
                        raise ValueError(
                            'Arguments must be specified as name=type')
                    try:
                        t = types[t]
                    except KeyError:
                        raise ValueError(f'Unknown type: {t}.')
                    args[n] = t

                defs.add(name, **args)
        return defs

