************
Wevis server
************

.. currentmodule:: wevis

A wevis server uses several threads:

- A single :class:`Server`, which manages a listener, manager, and room.
- A single :class:`Listener`, which listens for new connections.
- A single :class:`Manager`, which passes messages from and to connections.
- A single, custom, :class:`Room` implementation which receives and can respond to client messages.

All threads except the ``Server`` are started and managed by the Server.
Most of the work is done by the ``Manager``, (which does the actual sending and receiving of messages) and the ``Room`` (which contains the logic about how to respond to messages).

.. autoclass:: User

.. autoclass:: Room

.. autoclass:: Server

.. autoclass:: Listener

.. autoclass:: Manager

