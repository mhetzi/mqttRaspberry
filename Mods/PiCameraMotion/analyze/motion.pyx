# cython: language_level=3
# cython: cdivision=True
import numpy as np
cimport numpy as np
cimport cython
from libc.stdint cimport uintptr_t
from libc.stdlib cimport malloc, free
from libc.string cimport memset
from cpython.mem cimport PyMem_Malloc, PyMem_Realloc, PyMem_Free
from libc.math cimport floor, ceil, round, log2

from collections import deque

from scipy import ndimage

cdef packed struct sBLOCK:
    np.int8_t x
    np.int8_t y
    np.uint16_t sad 

ctypedef sBLOCK BLOCK

cdef inline int int_max(int a, int b): return a if a >= b else b
cdef inline int int_min(int a, int b): return a if a <= b else b
cdef inline double bit_length(int number): return log2(number)+1

cdef class MotionDedector:

    cdef np.int16_t window, area, frames
    cdef np.int16_t rows, cols
    cdef np.ndarray noise, field
    cdef object _last_frames
    cdef int last

    def __init__(self, np.int16_t rows, np.int16_t cols, np.int16_t window=10, np.int16_t area=25, np.int16_t frames=4):
        self.window = window
        self.area = area
        self.frames = frames
        self._last_frames = deque(maxlen=window)
        self.rows = rows
        self.cols = cols
        self.noise = np.zeros([self.rows, self.cols],dtype=np.short)
        self.last = -10

    cdef int count_longest(self, bint value):
            cdef np.uint16_t max
            cdef np.uint16_t now
            for d in self._last_frames:
                if d:
                    now += 1
                else:
                    if max < now:
                        max = now
                        now = 0
            return max

    cdef int analyze(self, np.ndarray a) except -1000:
        """Runs once per frame on a 16x16 motion vector block buffer (about 5000 values).
        Must be faster than frame rate (max 100 ms for 10 fps stream).
        Sets self.trigger Event to trigger capture.
        """

        # the motion vector array we get from the camera contains three values per
        # macroblock: the X and Y components of the inter-block motion vector, and
        # sum-of-differences value. the SAD value has a completely different meaning
        # on a per-frame basis, but abstracted over a longer timeframe in a mostly-still
        # video stream, it ends up estimating noise pretty well. Accordingly, we
        # can use it in a decay function to reduce sensitivity to noise on a per-block
        # basis

        # accumulate and decay SAD field
        cdef double bitl = bit_length(self.window)-2
        cdef np.int16_t shift = int_max( <int> bitl ,0)
        self.noise -= ( self.noise >> shift ) + 1 # decay old self.noise
        self.noise = np.add(self.noise, a['sad'] >> shift).clip(0)

        # then look for motion vectors exceeding the length of the current mask
        a = np.sqrt(
            np.square(a['x'].astype(np.float)) +
            np.square(a['y'].astype(np.float))
            ).clip(0, 255).astype(np.uint8)
        #self.field = a

        # look for the largest continuous area in picture that has motion
        cdef np.ndarray mask = (a > (self.noise >> 4)) # every motion vector exceeding current noise field
        labels,count = ndimage.label(mask) # label all motion areas
        cdef np.ndarray sizes = ndimage.sum(mask, labels, range(count + 1)) # number of MV blocks per area
        cdef int largest = np.sort(sizes)[-1] # what's the size of the largest area

        # Do some extra work to clean up the preview overlay. Remove all but the largest
        # motion region, and even that if it's just one MV block (considered noise)
        #mask = (sizes < max(largest,2))
        #mask = mask[labels] # every part of the image except for the largest object
        #self.field = mask

        # TODO: all the regions (and small movement) that we discarded as non-essential:
        # should feed that to a subroutine that weights that kind of movement out of the
        # picture in the future for auto-adaptive motion detector

        # does that area size exceed the minimum motion threshold?
        motion = (largest >= self.area)
        # then consider motion repetition
        self._last_frames.append(motion)

        cdef int longest_motion_sequence = self.count_longest(True)

        #return (motion, longest_motion_sequence >= self.frames)
        return 0 if not motion else longest_motion_sequence

    def analyse(self, a) -> (bool, int):
        cdef int t = self.analyze(a)
        cdef bint changed = t != self.last
        self.last = t
        return changed, t