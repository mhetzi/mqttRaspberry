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
    np.int16_t row
    np.int16_t col
    np.uint16_t c

ctypedef rBLOCK retBlock

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

@cython.boundscheck(False) # turn off bounds-checking for entire function
@cython.wraparound (False) # turn off negative index wrapping for entire function
cdef subtractMask(np.ndarray[BLOCK, ndim=2] arr, np.int16_t rows, np.int16_t cols, np.ndarray[BLOCK, ndim=2] mask):
    cdef np.int32_t v = 0
    for r in range(rows):
        for c in range(cols):
            v = arr[r,c].sad - mask[r,c].sad
            if v < 0:
                v = 0
            arr[r,c].sad = v
    return arr

def hotBlock(a, np.int16_t rows, np.int16_t cols, np.int16_t minNoise, np.ndarray[BLOCK, ndim=2] block_mask=None):
    #print("Rows: Typ: {}, länge: {}".format(a.__class__.__name__, rows))
    #print("Cols: Typ: {}, länge: {}".format(a[0].__class__.__name__, cols))
    #print("Data: Typ: {}, Data: {}".format(a[0][0].__class__.__name__, a[0][0]))
    cdef retBlock meh
    meh.b.x   = 0
    meh.b.y   = 0
    meh.b.sad = 0
    meh.c     = 0
    if block_mask is not None:
        a = subtractMask(a, rows, cols, block_mask)
    meh = chotBlock(a, rows, cols, minNoise)

    #print("Return: Typ: {}, länge: {}".format(meh.__class__.__name__, rows))
    #print(meh.__class__.__name__)
    return meh.b.x, meh.b.y, meh.b.sad, meh.c, meh

def init_block_mask(np.int16_t rows, np.int16_t cols):
    cdef np.ndarray ret = np.zeros([rows, cols], dtype=[('x', 'i1'),
        ('y', 'i1'),
        ('sad', 'u2'),])
    return ret

def update_block_mask(retBlock new_limit, np.ndarray[BLOCK, ndim=2] block_mask):
    block_mask[new_limit.b.x, new_limit.b.y].sad = new_limit.b.sad

def build_block_mask(array, rows, cols):
    cdef np.ndarray ret = np.zeros([rows, cols], dtype=[('x', 'i1'),
        ('y', 'i1'),
        ('sad', 'u2'),])
    for x in range( rows ):
        for y in range( cols ):
            ret[x,y] = array[x][y]
    return ret