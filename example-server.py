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

        elif message.name == 'PleaseMayIHaveSomeFloats':
            nf = message.get('doubles')
            nd = message.get('singles')

            reply = wevis.Message('SomeFloats')
            reply.set(doubles=[x / 10 for x in range(nd)])
            reply.set(singles=[x / 10 for x in range(nf)])
            connection.queue(reply)

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
