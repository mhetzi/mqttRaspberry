# -*- coding: utf-8 -*-

import numpy as np

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

import pyximport; pyximport.install()
import Mods.PiCameraMotion.analyze.hotblock

class Analyzer(cama.PiAnalysisOutput):
    motion_call = None
    logger = None
    processed = 0

    def __init__(self, camera, size=None):
        super(Analyzer, self).__init__(camera, size)
        self.cols = None
        self.rows = None

    def write(self, b):
        result = super(Analyzer, self).write(b)
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
        self.analyze(
                np.frombuffer(b, dtype=cama.motion_dtype).\
                reshape((self.rows, self.cols)))
        return result

    def analyze(self, a: cama.motion_dtype):
        self.cythonHotBlock(a)
    
    def cythonHotBlock(self, a):
        hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(a, self.rows, self.cols)
        self.logger.info("(x,y,val) = (%d,%d,%d) ", hottestBlock[0],hottestBlock[1],hottestBlock[2])
        self.processed += 1

    def hotBlock(self, a):
        hottestBlock = [0,0,0]
        #print("   Columns    ")
        #print( list(range(0, len(a[0]))) )
        rows = len(a)
        for x in range(0, rows):
            row = a[x]
            cols = len(row)
            #print(x, end = ": ")
            for y in range(0, cols):
                col = row[y]
                hottness = col[2]
                if hottestBlock[2] < hottness:
                    hottestBlock = [x,y,hottness]
                    #print("H", end="")
                #print(hottness, end=" ")
            #print("")
        self.logger.info("(x,y,val) = (%d,%d,%d) ", hottestBlock[0],hottestBlock[1],hottestBlock[2])
        self.processed += 1


    def getTotalChanged(self, a):
        added = 0
        x = np.square(a['x'].astype(np.float))
        for xx in x:
            for xxx in xx:
                added += xxx
        y = np.square(a['y'].astype(np.float))
        for yy in y:
            for yyy in yy:
                added += yyy
        self.logger.info("Changed: %d", added)
