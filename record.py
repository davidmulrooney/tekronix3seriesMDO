 #! /usr/bin/env python 
# -*- coding: utf-8 -*-

"""
Python script to remotely control a Tektronix 3-Series MDO oscilloscope.
"""

import socket
import signal
import csv
import time
from datetime import datetime as dt
import re

IP = "192.168.1.2" # Defined standard IP Gateway between the Oscilloscope and Users laptop 
PORT = 4000 # Defined standard PORT between the Oscilloscope and Users laptop
while True:
    try:
        testTime = float(input('Enter Test duration in seconds: '))  # Try to convert input to a float
        if testTime <= 0:
            print("Test duration must be greater than 0. Please try again.")
            continue
        break  # Exit the loop if input is valid
    except ValueError:
        print("Invalid input! Please enter a numeric value.")
run = True  # The loop runs until the user presses Ctrl-C 
now = dt.now().strftime("%d %b %Y %H-%M-%S")
logfile = str(input('Enter file name: ')) + '.csv'
if logfile == '.csv':
    logfile = f'{now} log.csv' # Name of .csv file the data gets logged into.
logfile = re.sub(r'[\/:*?"<>|]', '-', logfile)
print(f"Logfile name set to: {logfile}")

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ OSC SETUP ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
mathFUNCTION = '"(CH1/CH2)"' # RMS Voltage / RMS Current = Impedance (Math Function)
mathLabel = '"MF Impedance"' # MF = Math Function
mathPosition = '0E+00' # Math position works initially but moves around itself on the oscilloscope
currentLabel = '"Current"' # RMS Current
currentPosition = '0E+00' # Vertical Origin Line
voltageLabel = '"Voltage"' # RMS Voltage
voltagePosition = '0E+00' # Vertical Origin Line
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

def signal_handler(signum): # Handles Ctrl-C signal to stop the loop.
    global run
    print(f"Signal {signal.strsignal(signum)} received ... stopping")
    run = False

def check_trigger_status(socket): # Checks if the oscilloscope is triggered.
    socket.send(b"TRIGger:STAte?\n")
    answer = socket.recv(1024).decode().strip()
    return answer

input_buffer = 2 * 1024 # Buffer size for receiving data

# Establish socket connection
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to {IP}, port {PORT} ...")
    s.connect((IP, PORT)) # Connects to the oscilloscope with the given IP and port
    print("Connection successful.") # Message upon successful connection
except Exception as e: 
    print(f"Failed to connect to the oscilloscope: {e}") # Message upon successful connection
    exit(1)

# Query oscilloscope ID
try:
    s.send(b"*idn?\n") # Requests Oscilloscope ID
    answer = s.recv(input_buffer).decode().strip() 
    print(f"Connected to {answer}") # Oscilloscope ID
except Exception as e:
    print(f"Error communicating with the oscilloscope: {e}") 
    s.close()
    exit(1) 

# Configure oscilloscope (commands list can be expanded)
commands = [
    "*RST\n", # Reset oscilloscope to default settings
    ":HORIZONTAL:SCALE 20E-6\n", # Horizontal scale
    ":DISplay:PERSistence OFF\n", # Turns off display persistence
    ":SELect:CH1 1\n", # Selects Channel 1 for RMS Voltage
    f":CH1:LABel {voltageLabel};\n", # Labels Channel 1 as Voltage 
    ":SELect:CH2 2\n", # Selects Channel 2 for RMS Current
    ":CH2:PRObe:DEGAUss;\n", # Degausses the current probe on Channel 2
    f":CH2:LABel {currentLabel};\n", # Labels Channel 2 as Current
    ":TRIGger:A:TYPe EDGE;MODe NORMal;EDGE:SOUrce CH2; EDGE:SLOpe RISE\n", # Sets trigger settings
    ":TRIGger:A:LOWerthreshold:CH2 0.1\n", # Trigger threshold of 0.1A on Channel 2
    ":SELect:MATH 3\n", # Adds Math Function
    ":DISPlay:MATH ON\n", # Displays it on screen
    ":MATH:TYPe ADVANCED; SOUrce1 CHANnel1; SOUrce2 CHANnel2\n", # lists channels used by the math function
    f":MATH:DEFINE {mathFUNCTION}; LABEL {mathLabel}\n", # Labels the function and sets the calculation as Vrms/Irms
    ":MEASUREMENT:MEAS1:TYPE RMS; STATE ON; SOURCE1 CH1\n", # Sets MEAS1 as Vrms (Voltage)
    ":MEASUREMENT:MEAS2:TYPE RMS; STATE ON; SOURCE1 CH2\n", # Sets MEAS2 as Irms (Current)
    ":MEASUREMENT:MEAS3:TYPE FREQUENCY; STATE ON; SOURCE1 CH1\n", # Sets MEAS3 as frequency
    ":MEASUREMENT:MEAS4:TYPE PHAse; STATE ON; SOURCE1 CH1; SOURCE2 CH2\n", # Sets MEAS4 as phase
    ":MEASUREMENT:MEAS5:TYPE MEAN; STATE ON; SOURCE1 MATH\n", # Sets MEAS5 as impedance
    f"MATH:VERTical:POSITION {mathPosition}\n", # Sets math function's vertical position
    f"CH2:VERTical:POSITION {currentPosition}\n", # Sets vertical position for current
    f"CH1:VERTical:POSITION {voltagePosition}\n", # Sets vertical position for voltage
    "CH2:SCALE 0.2\n", # Current scale 0.2A/div
    "CH1:SCALE 20\n", # Voltage scale 1V/div
    "ACQuire:STOPAfter RUNSTop\n", # Stop acquisition when finished
    "CLEAR\n", # Clears any existing data
    "ACQuire:STATE RUN\n" # Starts data acquisition
]

for command in commands: # Sends each of the commands in the 'command' list to configure the oscilloscope
    try:
        s.send(command.encode())
    except Exception as e: # Error message
        print(f"Failed to send command {command.strip()}: {e}") # Message printed if an error occurs 


# Wait for the trigger to be activated
while True:
    trigger_status = check_trigger_status(s)
    print(f"Trigger Status: {trigger_status}")
    if trigger_status == "TRIGGER":
        print("Trigger activated, starting acquisition...")
        break
    time.sleep(0.1)  # Check trigger every 0.1 seconds

# Set up CSV logging
with open(logfile, 'w', newline='') as csvfile:
    csvwriter = csv.writer(csvfile, delimiter=',')
    csvwriter.writerow(['Time', 'VRMS', 'IRMS', 'Freq', 'Phase', 'Impedance'])
    signal.signal(signal.SIGINT, signal_handler)  # Set signal handler for Ctrl-C

    start_time = time.time()

    while run and (time.time() - start_time) <= testTime:
        now = time.time() - start_time  # Calculate elapsed time
        try:
            # Retrieve measurements from the oscilloscope
            measurements = []
            for i in range(1, 6):
                query = f"MEASUrement:MEAS{i}:VALue?\n"
                s.send(query.encode())
                answer = s.recv(input_buffer)
                try:
                    value = float(answer.decode())
                    if value == 9.91e+37:  # NAN value from oscilloscope indicates measurement not ready
                        print("Measurement not ready, skipping ...")
                        time.sleep(0.1)  # Wait for 0.1s before retrying
                        continue
                    measurements.append(value)
                except ValueError:
                    print(f"Failed to parse measurement {i}")
                    measurements.append(None)

            if len(measurements) == 5:
                print(f"{now:.6f}: Vrms: {measurements[0]} V, IRMS: {measurements[1]} A, "
                      f"Freq: {measurements[2]} Hz, Phase: {measurements[3]} deg, "
                      f"Impedance: {measurements[4]}")
                csvwriter.writerow([now] + measurements)

            time.sleep(0.01)  # Wait briefly between measurements
        except Exception as e:
            print(f"Error during measurement acquisition: {e}")

# Stop acquisitions after exiting the loop
try:
    s.send(b"ACQuire:STATE STOP\n")
    print("Acquisition stopped.")
except Exception as e:
    print(f"Error stopping acquisition: {e}")

s.close()

def add_column_v_over_i(input_file, output_file): # Calculates and adds a column for V/I (Impedance) in the CSV file.
    with open(input_file, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        rows = list(csvreader) 

    if rows:
        rows[0].append("V/I")  # Add header for new column

        for i in range(1, len(rows)):
            try:
                voltage = float(rows[i][1])
                current = float(rows[i][2])
                v_over_i = voltage / current if current != 0 else None
            except (ValueError, IndexError):
                v_over_i = None
            rows[i].append(v_over_i)

    with open(output_file, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerows(rows)

    print(f"Processed file saved as: {output_file}")
# Process and save data with calculated V/I column
add_column_v_over_i(logfile, logfile)