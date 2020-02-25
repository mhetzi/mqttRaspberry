# cython: language_level=3
# cython: cdivision=True
import numpy as np
cimport numpy as np
cimport cython
from libc.stdint cimport uintptr_t
from libc.stdlib cimport malloc, free
from libc.string cimport memset
from cpython.mem cimport PyMem_Malloc, PyMem_Realloc, PyMem_Free
from libc.math cimport floor, ceil, round

cdef packed struct sBLOCK:
    np.int8_t x
    np.int8_t y
    np.uint16_t sad

ctypedef sBLOCK BLOCK

cdef packed struct rBLOCK:
    BLOCK b
    np.int16_t row
    np.int16_t col
    np.uint16_t c

ctypedef rBLOCK retBlock

cdef packed struct zeroMapHandleIntern:
    np.uint16_t** zeroMapData
    np.int16_t rows
    np.int16_t cols

ctypedef zeroMapHandleIntern* zeroMapHandleInt
ctypedef uintptr_t zeroMapHandle

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound (False) # turn off negative index wrapping for entire function
cdef retBlock chotBlock(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols, np.int16_t minNoise):
    cdef retBlock hotest
    hotest.b.x = 0
    hotest.b.y = 0
    hotest.b.sad = 0
    hotest.c = 0
    hotest.row = 0
    hotest.col = 0
    cdef np.int16_t r
    cdef np.int16_t c
    cdef BLOCK b
    for r in range(rows):
        for c in range(cols):
            b = arr[r, c]
            if b.sad <= minNoise:
                continue
            if hotest.b.sad < b.sad:
                hotest.b.x = b.x
                hotest.b.y = b.y
                hotest.b.sad = b.sad
                hotest.col = c
                hotest.row = r
            if b.sad > minNoise:
                hotest.c += 1
    return hotest

def hotBlock(a, np.int16_t rows, np.int16_t cols, np.int16_t minNoise):
    #print("Rows: Typ: {}, länge: {}".format(a.__class__.__name__, rows))
    #print("Cols: Typ: {}, länge: {}".format(a[0].__class__.__name__, cols))
    #print("Data: Typ: {}, Data: {}".format(a[0][0].__class__.__name__, a[0][0]))
    cdef retBlock meh
    meh.b.x   = 0
    meh.b.y   = 0
    meh.b.sad = 0
    meh.c     = 0
    meh = chotBlock(a, rows, cols, minNoise)

    #print("Return: Typ: {}, länge: {}".format(meh.__class__.__name__, rows))
    #print(meh.__class__.__name__)
    return meh.b.x, meh.b.y, meh.b.sad, meh.c, meh

cdef class ZeroMap:

    cdef np.uint16_t** zeroMapData
    cdef np.uint16_t** lastFrame
    cdef np.int16_t rows, cols
    cdef bint subtractLast

    def __init__(self, rows, cols):
        cdef size_t size = sizeof(np.uint16_t) * rows * cols

        self.rows = rows
        self.cols = cols
        self.zeroMapData = <np.uint16_t**> PyMem_Malloc(sizeof(np.uint16_t*) * rows)
        self.lastFrame = <np.uint16_t**> PyMem_Malloc(sizeof(np.uint16_t*) * rows)
        
        if self.zeroMapData != NULL:
            for r in range(self.rows):
                self.zeroMapData[r] =  <np.uint16_t*> PyMem_Malloc(sizeof(np.uint16_t) * cols)
                self.lastFrame[r] =  <np.uint16_t*> PyMem_Malloc(sizeof(np.uint16_t) * cols)

    def __del__(self):
        if self.zeroMapData != NULL:
            for r in range(self.rows):
                PyMem_Free(self.zeroMapData[r])
            PyMem_Free(self.zeroMapData)
        
        if self.lastFrame != NULL:
            for r in range(self.rows):
                PyMem_Free(self.lastFrame[r])
            PyMem_Free(self.lastFrame)
    
    def activateLastFrame(self, bint active):
        self.subtractLast = active

    @cython.boundscheck(False) # turn off bounds-checking for entire function
    @cython.wraparound (False) # turn off negative index wrapping for entire function
    def trainZeroMap(self, np.ndarray[BLOCK, ndim=2] arr):
        cdef bint hasChanged = False
        cdef np.uint16_t v = 0

        if self.zeroMapData != NULL:
            for r in range(self.rows):
                for c in range(self.cols):
                    v = arr[r,c].sad
                    if v > self.zeroMapData[r][c]:
                        self.zeroMapData[r][c] =  <np.uint16_t> ceil(v + ( v / 100 * 15 ))
                        #print(self.zeroMapData[r][c])
                        hasChanged = True

        return hasChanged

    @cython.boundscheck(False) # turn off bounds-checking for entire function
    @cython.wraparound (False) # turn off negative index wrapping for entire function
    def saveZeroMap(self) -> dict:
        if self.zeroMapData == NULL:
            print("!!! SAVE FAILED zeroMapData is NULL !!!")
            return {}
        arr = {}
        for r in range(self.rows):
            arr[str(r)] = {}
            for c in range(self.cols):
                arr[str(r)][str(c)] = self.zeroMapData[r][c]
                #print(self.zeroMapData[r][c])
        return arr

    @cython.boundscheck(False) # turn off bounds-checking for entire function
    @cython.wraparound (False) # turn off negative index wrapping for entire function
    def trainConvertToDict(self, np.ndarray[BLOCK, ndim=2] arr):
        d = {}
        for r in range(self.rows):
            d[str(r)] = {}
            for c in range(self.cols):
                d[str(r)][str(c)] = arr[r,c].sad
                #print(self.zeroMapData[r][c])
        return d
    
    def trainFromDict(self, d: dict):
        for r in range(self.rows):
            for c in range(self.cols):
                v = d[str(r)][str(c)]
                if v > self.zeroMapData[r][c]:
                    self.zeroMapData[r][c] = <np.uint16_t> ceil(v + ( v / 100 * 15 ))


    def loadZeroMap(self, arr: dict):
        if self.zeroMapData == NULL:
            print("!! LOAD FAIL, zeroMapData == NULL !!")
            return
        for r in range(self.rows):
            row =  arr.get(str(r), None)
            if row is None:
                continue
            for c in range(self.cols):
                self.zeroMapData[r][c] = row.get(str(c), 0)

    @cython.boundscheck(False) # turn off bounds-checking for entire function
    @cython.wraparound (False) # turn off negative index wrapping for entire function
    cdef _subtractMask(self, np.ndarray[BLOCK, ndim=2] arr):
        if self.zeroMapData == NULL:
            return arr

        cdef np.int32_t v = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.subtractLast > 0:
                    v -= self.lastFrame[r][c]
                    self.lastFrame[r][c] = arr[r,c].sad
                    if v < 0:
                        v *= -1
                v = arr[r,c].sad - self.zeroMapData[r][c]
                if v < 0:
                    v = 0
                arr[r,c].sad = v
        return arr

    def subtractMask(self, np.ndarray[BLOCK, ndim=2] arr):
        return self._subtractMask(arr)