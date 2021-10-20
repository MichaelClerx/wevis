#!/usr/bin/env python3
"""
Very simple user class.
"""


class User(object):
    """
    A user of the server.

    Server-side code built on wevis can override this class and add in extra
    properties.

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
