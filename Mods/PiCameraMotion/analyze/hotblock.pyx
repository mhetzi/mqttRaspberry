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
    for r in range(rows):
        for c in range(cols):
            b = arr[r][c]
            if hotest.SAD < b.SAD:
                hotest = b
    return hotest

def hotBlock(a):
    rows = len(a)
    print("Rows: Typ: {}, länge: {}".format(a.__class__.__name__, rows))
    cols = len(a[0])
    print("Cols: Typ: {}, länge: {}".format(a[0].__class__.__name__, cols))
    try:
        meh = chotBlock(a, rows, cols)            # here you can put your code
    except Exception as e:
        print(e)                # this prints error message   
        print(type(e).__name__)
    print(meh.__class__.__name__)
    return meh.x, meh.y, meh.SAD