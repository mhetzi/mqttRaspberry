# -*- coding: utf-8 -*-

class NullOutput(object):
    def __init__(self):
        self.size = 0

    def write(self, s):
        self.size += len(s)

    def flush(self):
        print('%d bytes would have been written' % self.size)

    def reset(self):
        self.size = 0
