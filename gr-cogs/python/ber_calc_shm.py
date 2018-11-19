#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright 2018 gr-cogs author.
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import numpy as np
from gnuradio import gr
import pmt
from shmem import shm_mem

class ber_calc_shm(gr.sync_block):
    """
    docstring for block ber_calc_shm
    """
    def __init__(self, channel_id):
        gr.sync_block.__init__(self,
            name="ber_calc_shm",
            in_sig=[np.float32],
            out_sig=[np.float32]
        )
        
        # class parameters
        self.transmit_vector = None                     # original transmitted vector 
        self.transmit_vector_instance_count = 0         # number of times transmit vector is repeated for duration of burst
        self.transmit_vector_length = 0                 # length of the transmit vector
        self.transmit_vector_preamble_length = 0        # length of the preamble at the head of the transmit vector
        self.frame_id = None                            # frame id for reading
        self.channel_id = channel_id                    # channel ID
        self.sample_rate_hz = 0                         # incoming sample rate
        self.center_freq_hz = 0                         # incoming center freq
        self.work_counter = 0                           # counter for number of times work completed
        self.process = False                            # flag to demod samples
        self.use_full_preamble = False                   # use entire preamble for correlation or subset
        self.bits_from_preamable_to_use = 64            # if not using entire preamble, use N bits subset

        # init shared memory
        self.cbp = shm_mem(channel_id=0, write_permissions=False)
        self.read_cbp()

        self.bit_counter = 0

    def read_cbp(self):

        # read channel info
        channel_header =  self.cbp.read_channel_header()
        print ('[Channel Info]')
        print ('---- [Channel ID] ', channel_header.channel_id)
        print ('---- [Active Pointer] ', channel_header.active_pointer)
        print ('---- [Source] ', channel_header.source)
        print ('---- [Center Freq (MHz)] ', channel_header.center_freq_hz/1e6)
        print ('---- [Sample Rate (Ksps] ', channel_header.sample_rate_hz/1e3)

        # store channel data
        self.active_pointer_index = channel_header.active_pointer
        self.sample_rate_hz = channel_header.sample_rate_hz
        self.center_freq_hz = channel_header.center_freq_hz

        # read frame info
        frame_index = 0+ self.cbp.channel_header_size_bytes
        frame_header =  self.cbp.read_frame_header(frame_index)
        print ('[Frame Info]')
        print ('---- [Frame ID] ', frame_header.frame_id)
        print ('---- [Frame Index] ', frame_index)
        print ('---- [Length] ', frame_header.length)
        print ('---- [Type] ', frame_header.type)
        print ('---- [Number of Instances] ', frame_header.number_of_instances)
        print ('---- [Preamble Length] ', frame_header.preamble_length)

        # store frame data
        self.transmit_vector = self.cbp.read_int32_vector(frame_header.length, frame_header.data_index)
        self.transmit_vector_length = frame_header.length
        self.transmit_vector_instance_count = frame_header.number_of_instances
        self.transmit_vector_preamble_length = frame_header.preamble_length
        self.frame_id = frame_header.frame_id

        print ('Converting stored transmit vector to binary representation')
        self.convert_transmit_vector_to_binary()
        print ('Done converting stored transmit vector to binary representation')

        # setup preamble for correlation
        if len(self.preamble_bits) > 0:
            if self.use_full_preamble:
                self.bits_from_preamable_to_use = len(self.preamble_bits)
                self.preamble_start_index = 0
                self.preamble_stop_index = self.bits_from_preamable_to_use
            else:
                start_index_from_preamble = np.random.randint(20, len(self.preamble_bits-20))
                self.preamble_start_index = start_index_from_preamble
                self.preamble_stop_index = start_index_from_preamble + self.bits_from_preamable_to_use

            print('Using preamble of length ' + str(len(self.preamble_bits[self.preamble_start_index:self.preamble_stop_index])) + ' bits')
            print('preamble[', self.preamble_start_index ,':', self.preamble_stop_index, ']: ', self.preamble_bits[self.preamble_start_index:self.preamble_stop_index])
        
        print('\n\n\n')
    

    def convert_transmit_vector_to_binary(self):
        self.preamble_bits = self.unpack_k_bits(8, self.transmit_vector[0:self.transmit_vector_preamble_length])
        self.payload_bits = self.unpack_k_bits(8, self.transmit_vector[self.transmit_vector_preamble_length:self.transmit_vector_length])

        self.total_bits_transmitted = int(self.transmit_vector_length * self.transmit_vector_instance_count)
        

    def unpack_k_bits(self, k, bytes, fname = None):

        bits = np.zeros(k * len(bytes))
        n = 0
        
        # for all byte values
        for i in range( len(bytes) ):
            t= bytes[i]

            # convert to 8 bit binary representation
            j = k-1
            while j >= 0:
                bits[n] = (t >> j) & 0x01
                j = j - 1
                n = n+1

        return bits


    def find_subsequence(self, seq, subseq):
        target = np.dot(subseq, subseq)
        candidates = np.where(np.correlate(seq, subseq, mode='valid') == target)[0]
        
        # check for false positives
        check = candidates[:, np.newaxis] + np.arange(len(subseq))
        mask = np.all((np.take(seq, check) == subseq), axis=-1)

        return candidates[mask]


    def work(self, input_items, output_items):
        
        num_input_items = len(input_items[0])
        out = output_items[0]

        # check to see if cbp has been updated
        if self.work_counter % 100 == 0:
            frame_index = 0+ self.cbp.channel_header_size_bytes
            frame_header = self.cbp.read_frame_header(frame_index)
            if frame_header.frame_id != self.frame_id:
                print(' New Frame! Updating data from channel backplane')
                self.read_cbp()
            self.work_counter = 0

        self.work_counter += 1

        # if tag exists: demod->decode->map->compare
        tags = self.get_tags_in_window(0, 0, num_input_items)

        # look for tags to indicate burst
        for tag in tags:
            tag_key = pmt.symbol_to_string(tag.key)
            
            if (tag_key == "Begin Burst"):
                self.process = True
                print('Attempting Demod on Burst')
            elif (tag_key == "End Burst"):
                self.process = False
                print('Stopping Demod, Burst Ended')
                print ('Total bits received / expected:', self.bit_counter, self.total_bits_transmitted) 
                self.bit_counter = 0

        # no burst detected, dont process samples
        if self.process == False:
            output_items[0][:] = np.zeros(num_input_items)
            return len(output_items[0])

        self.bit_counter += num_input_items


        if num_input_items > self.bits_from_preamable_to_use:
            #print ('\n\n Preamble: ', list(self.preamble_bits[0:self.bits_from_preamable_to_use]), '\n\n Seq: \n\n', list(input_items[0]) )
            correlations = self.find_subsequence(input_items[0], self.preamble_bits[self.preamble_start_index:self.preamble_stop_index])
            if len(correlations) > 0:    
                print ("============Correlated Preamble============ ", correlations)

                first_corr_input_index = correlations[0]
                last_corr_input_index = first_corr_input_index + self.bits_from_preamable_to_use

                bits_left_to_check = num_input_items - last_corr_input_index

                bits_left_unchecked_in_preamble = len(self.preamble_bits) -  self.preamble_stop_index

                # can only check preamble remainder bits
                input_index = last_corr_input_index + 1
                preamble_index = self.preamble_stop_index + 1
                error_count = 0

                bits_left_unchecked_in_payload = len(self.payload_bits)
                payload_index = 0

                #print (first_corr_input_index, last_corr_input_index, bits_left_to_check, len(self.preamble_bits), stop, bits_left_unchecked_in_preamble, bits_left_unchecked_in_payload)
                # ber on all bits

                while bits_left_to_check > 1:
                    # check remainder of preamble
                    print('BER on Preamble Number of Bits ' + str(bits_left_to_check))
                    while bits_left_unchecked_in_preamble > 1 and bits_left_to_check > 1:
                        #print('\n input index: ', input_index, '\n', 'preamble_index: ', preamble_index, '\n', 'bits left to check: ', bits_left_to_check, '\n', 'bits left in preamble: ', bits_left_unchecked_in_preamble, '\n')
                        if input_items[0][input_index] != self.preamble_bits[preamble_index]:
                            error_count+=1
                        
                        bits_left_to_check -=1
                        input_index +=1
                        preamble_index +=1
                        bits_left_unchecked_in_preamble -=1

                    preamble_index = 0
                    bits_left_unchecked_in_preamble = len(self.preamble_bits)


                    # check remainder of payload
                    print('BER on Payload Number of Bits ' + str(bits_left_to_check))
                    while bits_left_unchecked_in_payload > 1 and bits_left_to_check > 1:
                        if input_items[0][input_index] != self.payload_bits[payload_index]:
                            error_count+=1
                        
                        bits_left_to_check -=1
                        input_index +=1
                        payload_index +=1
                        bits_left_unchecked_in_payload -=1

                    payload_index = 0
                    bits_left_unchecked_in_payload = len(self.payload_bits)

                print('\n\n\n\n Error: ' + str(error_count) + ' out of ' + str(num_input_items - first_corr_input_index) )
                print(' Error Rate: ' + str (float(error_count)/float(num_input_items-first_corr_input_index)) + '\n\n')

        return len(output_items[0])
