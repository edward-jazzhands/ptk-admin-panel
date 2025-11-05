# make_zombie.py
import os
import time

for _ in range(2):
    pid = os.fork()
    if pid == 0:
        print("Child exiting...")
        os._exit(0)   # child exits immediately
else:
    for x in range(60):
        print(f"Parent sleeping... {x} sec elapsed")   
        time.sleep(1)
