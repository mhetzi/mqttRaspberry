import numpy as np
cimport numpy as np
cimport cython

cdef struct sBLOCK:
    np.int8_t x
    np.int8_t y
    np.uint16_t SAD

ctypedef sBLOCK BLOCK

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cdef BLOCK chotBlock(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols):
    cdef BLOCK hotest
    hotest.x = 0
    hotest.y = 0
    hotest.SAD = 0
    cdef np.uint16_t r
    cdef np.uint16_t c
    cdef BLOCK b
    for r in range(rows):
        for c in range(cols):
            b = arr[r][c]
            if hotest.SAD < b.SAD:
                hotest.x = b.x
                hotest.y = b.y
                hotest.SAD = b.SAD
    return hotest

def hotBlock(a, np.int16_t rows, np.int16_t cols):
    meh = chotBlock(a, rows, cols)
    return meh.x, meh.y, meh.SAD