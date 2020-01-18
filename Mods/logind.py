"""
from pydbus import SystemBus
bus = SystemBus()
proxy = bus.get(".login1", "/org/freedesktop/login1")

proxy.ListSessions()
=> [('c1', 42, 'gdm', 'seat0', '/org/freedesktop/login1/session/c1'),
    ('4', 1000, 'marcel', '', '/org/freedesktop/login1/session/_34'),
    ('2', 1000, 'marcel', 'seat0', '/org/freedesktop/login1/session/_32')]

import os
os.getuid()

"""