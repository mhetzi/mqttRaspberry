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
    cdef np.int16_t r
    cdef np.int16_t c
    for r in range(rows):
        for c in range(cols):
            b = arr[r][c]
            if hotest.SAD < b[2]:
                hotest.x = b[0]
                hotest.y = b[1]
                hotest.SAD = b[2]
    return hotest

def hotBlock(a, np.int16_t rows, np.int16_t cols):
    print("Rows: Typ: {}, länge: {}".format(a.__class__.__name__, rows))
    print("Cols: Typ: {}, länge: {}".format(a[0].__class__.__name__, cols))
    print("Data: Typ: {}, Data: {}".format(a[0][0].__class__.__name__, a[0][0]))
    meh = chotBlock(a, rows, cols)
    print("Return: Typ: {}, länge: {}".format(meh.__class__.__name__, rows))
    print(meh.__class__.__name__)
    return meh.x, meh.y, meh.SAD