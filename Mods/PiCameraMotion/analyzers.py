# -*- coding: utf-8 -*-

import numpy as np

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

import pyximport; pyximport.install()
import hotblock as HotBlock

class Analyzer(cama.PiMotionAnalysis):
    motion_call = None
    logger = None
    processed = 0

    def analyze(self, a: cama.motion_dtype):
        self.cythonHotBlock(a)
    
    def cythonHotBlock(self, a):
        hottestBlock = HotBlock.hotBlock(a, len(a), len(a[0]))
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
