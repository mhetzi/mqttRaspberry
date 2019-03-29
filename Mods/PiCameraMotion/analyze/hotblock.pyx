import numpy as np
cimport numpy as np
cimport cython

cdef struct BLOCK:
    np.int8_t x
    np.int8_t y
    np.uint16_t SAD

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
cdef BLOCK chotBlock(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols):
    cdef BLOCK hotest
    for r in range(rows):
        for c in range(cols):
            b = arr[r][c]
            if hotest.SAD < b.SAD:
                hotest = b
    return hotest

def hotBlock(a):
    meh = chotBlock(a, len(a), len(a[0]))
    return meh.x, meh.y, meh.SAD