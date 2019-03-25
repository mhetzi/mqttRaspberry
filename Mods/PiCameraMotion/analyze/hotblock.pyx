import numpy as np
cimport numpy as np
cimport cython

ctypedef (np.int8_t, np.int8_t, np.uint16_t) BLOCK

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
def hotBlock(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols):
    cdef BLOCK hotest = (0,0,0)
    for r in range(rows):
        for c in range(cols):
            b = arr[r][c]
            if hotest[2] < b[2]:
                hotest = b
    return hotest