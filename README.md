# "Where is Ben Nevis?" Client/Server IO

This repository contains a draft of ``wevis``, a Python module used to set up a server/client system for "Where is Ben Nevis", that lets Ben Nevis players query a remote server.
However, the code is written in such a way that it should be re-usable for other purposes.

## How does it work?

Users of ``wevis`` write two programs: a server and a client.
A single instance of the server program is started, and several clients can connect to it.
There is an initial password protected log-in, which is handled mostly by the server.
After this, the server and client communicate by sending ``wevis`` _messages_ back and forth over a TCP connection.
Each message is of a predefined type, and has a name and a fixed number of arguments.
Both server and client have a local copy of this list of user-defined message types.

### Parallelism

Maintaining the connection requires that the client and server are both written with some degree of parallelism.
Most of this is handled by ``wevis``, and examples are given below of how to do the rest.
Importantly, a TCP protocol is used which guarantees that messages arrive in the order they were sent.
Users do **not** need to handle the case where messages arrive out of order.

### Writing a server

To write a server, a user provides

- a method ``version_validator`` used to check compatibility when a client wants to connect
- a method ``user_validator`` used to check login credentials
- a subclass of ``wevis.Room`` that provides a method ``messages`` to define message types and a method ``handle(connection, message)`` to handle arriving messages.
- in most cases you'll also want to subclass ``wevis.User`` and use it to store user properties.

For example:

```
#!/usr/bin/env python3
import wevis

def version_validator(major, minor, revision):
    return major >= 1


def user_validator(username, password, salt):
    if username == 'michael' and password == wevis.encrypt('mypassword', salt):
        return wevis.User('michael')
    return False


class TimeRoom(wevis.Room):
    def handle(self, connection, message):
        if message.name == 'WhatTimeIsIt':
            import datetime
            t = datetime.datetime.now()
            connection.q('ItIs', hours=t.hour, minutes=t.minute)
        elif message.name == 'WhoAmI':
            connection.q('YouAre', name=connection.user.name)
        else:
            raise Exception(f'Unexpected message: {message}')


if __name__ == '__main__':
    import logging
    import sys
    wevis.set_logging_level(logging.DEBUG)
    logging.basicConfig(stream=sys.stdout)

    defs = wevis.DefinitionList.from_file('example-definitions')
    defs.instantiate()

    room = TimeRoom()
    server = wevis.Server(version_validator, user_validator, room)
    server.launch()
```

The message definitions can be writen in code:

```
    defs = wevis.DefinitionList()
    defs.add('WhatTimeIsIt')
    defs.add('ItIs', hours=int, minutes=int)
    defs.add('WhoAmI')
    defs.add('YouAre', name=str)
    defs.instantiate()
```

but in this example they are loaded from a plain text file:

```
# Time messages
WhatTimeIsIt
ItIs hours=int minutes=int

# Identity messages
WhoAmI
YouAre name=str
```

Here, the code for ``launch()`` simply starts and monitors the server thread:

```
    def launch(self):
        self.start()
        try:
            while self.is_alive():
                time.sleep(0.1)
        finally:
            self.stop()
        if self._exception:
            raise self._exception
```

Similar lines can be used to integrate the server thread in a larger program.

### Writing a client

Like the server, the ``Client`` class extends ``threading.Thread`` and can be used in a threaded application.
However, it can also be used in a "blocking" mode, for example as shown below:

```
#!/usr/bin/env python3
import wevis

import logging
import sys
logging.basicConfig(stream=sys.stdout)

defs = wevis.DefinitionList.from_file('example-definitions')
defs.instantiate()

version = (1, 0, 0)
client = wevis.Client(version, 'michael', 'mypassword')
try:
    client.start_blocking()

    client.q('WhoAmI')
    r = client.receive_blocking('YouAre')
    print(f'Username: {r.get("name")}')
    client.q('WhatTimeIsIt')
    r = client.receive_blocking('ItIs')
    print(f'It is {r.get("hours")}:{r.get("minutes")}')
finally:
    client.stop()
```

## Contributions

This software is based on an earlier project, "remote science", by Michael Clerx and Tom Hogewind.

## License

This code can be freely re-used and adapted.
See [LICENSE.txt](LICENSE.txt) for details.

