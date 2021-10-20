#!/usr/bin/env python3
#
# Example server code.
#
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

    defs = wevis.DefinitionList()
    defs.add('WhatTimeIsIt')
    defs.add('ItIs', hours=int, minutes=int)
    defs.add('WhoAmI')
    defs.add('YouAre', name=str)
    defs.instantiate()

    room = TimeRoom()
    server = wevis.Server(version_validator, user_validator, room)
    server.launch()
