import random
import time

def generate_live_patients():

    while True:
        patients = random.randint(40,150)

        yield patients

        time.sleep(3)