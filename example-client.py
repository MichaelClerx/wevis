#!/usr/bin/env python3
#
# Example client code (blocking).
#
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
    print(f'It is {r.get("hours"):02}:{r.get("minutes"):02}')

    client.q('PleaseMayIHaveSomeFloats', singles=4, doubles=3)
    r = client.receive_blocking('SomeFloats')
    print(f'Singles: {r.get("singles")}')
    print(f'Doubles: {r.get("doubles")}')

finally:
    client.stop()
