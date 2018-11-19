from __future__ import print_function    # (at top of module)

import numpy as np
import mmap
import os
import struct
import ctypes
from collections import namedtuple

FrameHeader = namedtuple("FrameHeader", "frame_id length type number_of_instances data_index preamble_length")
ChannelHeader = namedtuple("ChannelHeader", "channel_id active_pointer source center_freq_hz sample_rate_hz")


class shm_mem(object):

    # shared memory info
    path = '/dev/shm/cogmap-'
    file_descriptor = None

    # shared memory buffer info
    buffer = None
    open = False
    buffer_size = 62500 * mmap.PAGESIZE  #(typically page map is 4096 bytes

    # channel header info
    channel_header_size_bytes = 100
    channel_id = 0
    active_pointer = 0  # only writes will move this
    source = 't'        # 't' = transmit, 'r' = receive
    center_frequency_hz = 0.0
    sample_rate_hz = 0.0

    channel_id_index = 0
    active_pointer_index = 4
    source_index = 8
    center_frequency_hz_index = 12
    sample_rate_hz_index = 20

    # frame header info
    frame_header_size_bytes = 24


    def __init__(self, channel_id, write_permissions=False):

        # save channel_id
        self.channel_id = channel_id

        # Create the mmap instace with the following params:
        # fd: File descriptor which backs the mapping or -1 for anonymous mapping
        # length: Must in multiples of PAGESIZE (usually 4 KB)
        # flags: MAP_SHARED means other processes can share this mmap
        # prot: PROT_WRITE means this process can write to this mmap
        if not write_permissions:

            # open file disk space backing memory map
            self.file_descriptor = os.open(self.path+str(self.channel_id), os.O_RDONLY)

            # map
            self.buffer = mmap.mmap(self.file_descriptor, self.buffer_size, mmap.MAP_SHARED, mmap.PROT_READ)

            self.open = True

            self.source = 'r'


        else:

            # create file disk space for backing memory map
            self.file_descriptor = os.open(self.path + str(self.channel_id), os.O_CREAT | os.O_TRUNC | os.O_RDWR)

            # clear file
            assert os.write(self.file_descriptor, '\x00' * self.buffer_size) == self.buffer_size

            # map
            self.buffer = mmap.mmap(self.file_descriptor, self.buffer_size, mmap.MAP_SHARED, mmap.PROT_WRITE)

            self.open = True

            # channel header
            self.source = 't'


    def write_channel_header(self, center_frequency_hz = None, sample_rate_hz = None):

        ##-- Channel Header Specification --##
        # int32 channel_id
        # int32 active_pointer
        # char 1 source: 't' for tx, 'r' for rx
        # char 3 bytes reserved
        # float64 center frequency hz
        # float64 sample rate hz
        # 72 bytes reserved

        self.center_frequency_hz = center_frequency_hz
        self.sample_rate_hz = sample_rate_hz
        self.active_pointer = 0

        # --- int32 channel_id --- #
        self.write_int32(self.channel_id)

        # --- int32 active_pointer --- #
        self.write_int32(self.active_pointer)

        # --- char1 origin --- #
        self.write_string(self.source)

        # --- char3 RESERVED --- #
        for i in range(3):
            self.write_string('\x00')

        # --- float64 (IEEE 754-2008) center frequency --- #
        self.write_double(self.center_frequency_hz)

        # --- float64 (IEEE 754-2008) sample rate --- #
        self.write_double(self.sample_rate_hz)

        # --- 72 bytes RESERVED --- #
        for i in range(72):
            self.write_string('\x00')


    def read_channel_header(self):

        ##-- Channel Header Specification --##
        # int32 channel_id
        # int32 active_pointer
        # char 1 source: 't' for tx, 'r' for rx
        # char 3 bytes reserved
        # float64 center frequency hz
        # float64 sample rate hz
        # 72 bytes reserved

        # --- int32 length --- #
        channel_id_value = self.read_int32(self.channel_id_index)

        # --- int32 length --- #
        active_ptr_value = self.read_int32(self.active_pointer_index)

        # --- char1 origin --- #
        source_value = self.read_char(self.source_index)

        # --- float64 number_of_instances --- #
        center_freq_hz_value = self.read_double(self.center_frequency_hz_index)
        sample_rate_hz_value = self.read_double(self.sample_rate_hz_index)

        return ChannelHeader(channel_id_value, active_ptr_value, source_value, center_freq_hz_value, sample_rate_hz_value)


    def write_frame_header(self, frame_id, length, data_type, number_of_instances, preamble_length):

        ##-- Frame Header Specification --##
        # int32 frame_id
        # int32 length
        # char 1 type : 'i' for int, 'f' for float
        # char 3 bytes reserved
        # float64 number_of_instances
        # int32 preamble length

        if not self.open:
            print('Shared Memory is not available, cannot write header.')
            return

        # --- int32 frame id --- #
        self.write_int32(frame_id)

        # --- int32 length --- #
        self.write_int32(length)

        # --- char1 type --- #
        self.write_string(data_type)

        # --- char3 RESERVED --- #
        for i in range(3):
            self.write_string('\x00')

        # --- float64 length --- #
        self.write_double(number_of_instances)

        # --- int32 preamble length --- #
        self.write_int32(preamble_length)

        # index = self.active_pointer-self.frame_header_size_bytes
        # self.print_shmem_contents(self.frame_header_size_bytes, index=index)


    def read_frame_header(self, index=None):

        ##-- Frame Header Specification --##
        # int32 frame_id
        # int32 length
        # char 1 type : 'i' for int, 'f' for float
        # char 3 bytes reserved
        # float64 number_of_instances
        # int32 preamble length


        if not self.open:
            print('Shared Memory is not available, cannot read header.')
            return

        if index is None:
            index = self.active_pointer

        # self.print_shmem_contents(self.frame_header_size_bytes, index=index)

        # --- int32 frame_id --- #
        frame_id = self.read_int32(index)
        index = index + 4

        # --- int32 length --- #
        length = self.read_int32(index)
        index = index + 4

        # --- char1 type --- #
        type = self.read_char(index)
        index = index + 1

        # --- char3 RESERVED --- #
        index = index + 3

        # --- float64 number_of_instances --- #
        number_of_instances = self.read_double(index)
        index = index + 8

        # --- int32 length --- #
        preamble_length = self.read_int32(index)
        index = index + 4

        return FrameHeader(frame_id, length, type, number_of_instances, index, preamble_length)


    def move_active_pointer(self, N):

        # update channel header info
        if not self.open:
            print('Shared Memory is not available, cannot write int32.')
            return

        # move active pointer
        self.active_pointer = self.active_pointer + N

        # create int in shared mem
        i32_shmem_obj = ctypes.c_int.from_buffer(self.buffer, self.active_pointer_index)

        # set value of shared mem int to i
        i32_shmem_obj.value = self.active_pointer

        # validate shared memory was set
        assert i32_shmem_obj.value == self.active_pointer


    def print_shmem_contents(self, N, index = None):

        if index is None:
            index = self.active_pointer


        print('\n Printing Shared Memory Content')

        i = index
        while(i < index + N):
            print('  [', i ,'] = ', self.buffer[i])
            i += 1

        print('\n Finished Printing Shared Memory Content')


    def write_int32(self, i):

        if not self.open:
            print ('Shared Memory is not available, cannot write int32.')
            return

        # create int in shared mem
        i32_shmem_obj = ctypes.c_int.from_buffer(self.buffer, self.active_pointer)

        # set value of shared mem int to i
        i32_shmem_obj.value = i

        # validate shared memory was set
        assert i32_shmem_obj.value == i

        # move active pointer
        self.move_active_pointer(4)


    def read_int32(self, index = None):

        if index is None:
            return struct.unpack('i', self.buffer[self.active_pointer : self.active_pointer + 4])[0]
        else:
            return struct.unpack('i', self.buffer[index : index + 4])[0]


    def write_double(self, f):

        if not self.open:
            print ('Shared Memory is not available, cannot write double.')
            return

        # create float in shared mem
        f64_shmem_obj = ctypes.c_double.from_buffer(self.buffer, self.active_pointer)

        # set value of shared mem double(64bits) to f
        f64_shmem_obj.value = f

        # validate shared memory was set
        np.testing.assert_almost_equal(f64_shmem_obj.value, f, 6)

        # move active pointer
        self.move_active_pointer(8)


    def read_double(self, index=None):

        if index is None:
            return struct.unpack('d', self.buffer[self.active_pointer : self.active_pointer + 8])[0]
        else:
            return struct.unpack('d', self.buffer[index : index + 8])[0]


    def write_string(self, s):

        if not self.open:
            print ('Shared Memory is not available, cannot write char array.')
            return

        # determine space required for terminator
        charArray_shmem_obj = ctypes.c_char * len(s)

        # create char string in shared mem
        str_shmem_obj = charArray_shmem_obj.from_buffer(self.buffer, self.active_pointer)

        # set the value of the shared mem term obj
        str_shmem_obj.raw = s

        # move active pointer
        self.move_active_pointer(len(s))


    def read_char(self, index=None):

        if index is None:
            return struct.unpack('c', self.buffer[self.active_pointer : self.active_pointer + 1])[0]
        else:
            return struct.unpack('c', self.buffer[index : index + 1])[0]


    def write_f32_vector(self, f32_vector):

        # add each float32 to shared mem
        for f in f32_vector:
            self.write_float32(f)


    def read_f32_vector(self, N, index = None):

        if not self.open:
            print ('Shared Memory is not available, cannot read header.')
            return

        if index is None:
            index = self.active_pointer

        vector = np.frombuffer(self.buffer, dtype=np.float32, count=N, offset=index)

        # this explicit method is much slower
        # # create an empty numpy array
        # vector = np.empty(N, dtype=np.float32)
        #
        # # read each float into the respective array index
        # for i in range(N):
        #     vector[i] = self.read_float32(index)
        #     index = index + 4

        return vector


    def write_int32_vector(self, int32_vector):

        # add each int to shared mem
        for i in int32_vector:
            self.write_int32(i)


    def read_int32_vector(self, N, index=None):

        if not self.open:
            print ('Shared Memory is not available, cannot read header.')
            return

        if index is None:
            index = self.active_pointer

        # memory map from buffer into numpy array
        vector = np.frombuffer(self.buffer, dtype=np.int32, count=N, offset=index)

        # this explicit method is much slower
        #  create an empty numpy array
        # vector = np.empty(N, dtype=np.int32)
        #
        # # read each float into the respective array index
        # for i in range(N):
        #     vector[i] = self.read_int32(index)
        #     index = index + 4

        return vector


