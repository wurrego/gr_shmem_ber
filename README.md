# gr_shmem_ber
A simple GNU Radio Python block that reads data from shared memory to calculate BER in transmit burst

# Note on Shared Memory
Not the most efficient implementation, but quick to play around with alternative methods to socket based IPC between tx-rx applications  

		/dev/shm/cogmap-## must be initialized before running this application.

		This can be used in conjucation with python-qt5 tx example app  