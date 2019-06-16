import numpy as np
cimport numpy as np
cimport cython

cdef packed struct sBLOCK:
    np.int8_t x
    np.int8_t y
    np.uint16_t sad

ctypedef sBLOCK BLOCK

cdef packed struct rBLOCK:
    BLOCK b
    np.int16_t c

ctypedef rBLOCK retBlock

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cdef retBlock chotBlock(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols, np.int16_t minNoise):
    cdef retBlock hotest
    hotest.b.x = 0
    hotest.b.y = 0
    hotest.b.sad = 0
    hotest.c = 0
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
            if b.sad > minNoise:
                hotest.c += 1
    return hotest

def hotBlock(a, np.int16_t rows, np.int16_t cols, np.int16_t minNoise):
    #print("Rows: Typ: {}, länge: {}".format(a.__class__.__name__, rows))
    #print("Cols: Typ: {}, länge: {}".format(a[0].__class__.__name__, cols))
    #print("Data: Typ: {}, Data: {}".format(a[0][0].__class__.__name__, a[0][0]))
    meh = chotBlock(a, rows, cols, minNoise)
    #print("Return: Typ: {}, länge: {}".format(meh.__class__.__name__, rows))
    #print(meh.__class__.__name__)
    return meh.b.x, meh.b.y, meh.b.sad, meh.c