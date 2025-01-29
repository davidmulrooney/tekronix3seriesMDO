  import pyvisa  # PyVISA library for USB communication
import signal
import csv
import time
from datetime import datetime as dt
import re


instrumentIds = ["USB0::0x0699::0x052C::C053930::INSTR","USB0::0x0699::0x052C::C018620::INSTR"] #EQ068 and EQ031 Instrument IDs
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
reconnectDelay = 5


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ OSC SETUP ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
mathFunction = '"(CH1/CH2)"' # RMS Voltage / RMS Current = Impedance (Math Function)
mathLabel = '"MF Impedance"' # MF = Math Function
mathPosition = '0E+00' # Math position works initially but moves around itself on the oscilloscope
currentLabel = '"Current"' # RMS Current
currentPosition = '0E+00' # Vertical Origin Line
voltageLabel = '"Voltage"' # RMS Voltage
voltagePosition = '0E+00' # Vertical Origin Line
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

def signalHandler(signum, frame):
    global run
    print(f"Signal {signal.strsignal(signum)} received ... stopping")
    run = False

def waitForTrigger(scope):
    scope.timeout = 5000  # Set the timeout to 5 seconds
    triggerStatus = scope.query("TRIGGER:STATE?").strip()
    while triggerStatus not in ["TRIGGER", "READY"]:
        time.sleep(0.01)  # Wait for 100ms before retrying
        triggerStatus = scope.query("TRIGGER:STATE?").strip()
        if isinstance(triggerStatus, bytes):
            triggerStatus = triggerStatus.decode('utf-8')
    return triggerStatus

maxRetries = 5  

def connect_to_scope(instrument_ids):
    """ Attempt to connect to the oscilloscope from the list of instrument IDs. """
    for attempt in range(1, maxRetries + 1):
        try:
            print(f"Attempt {attempt}/{maxRetries} to connect to the oscilloscope...")
            rm = pyvisa.ResourceManager()
            available_resources = rm.list_resources()
            print(f"Available VISA resources: {available_resources}")
            
            for resource_id in instrument_ids:
                if resource_id in available_resources:
                    try:
                        scope = rm.open_resource(resource_id)
                        idn_response = scope.query("*IDN?").strip()
                        print(f"Connected to {idn_response} using {resource_id}")
                        return scope
                    except Exception as e:
                        print(f"Failed to connect to {resource_id}: {e}")
        except Exception as e:
            print(f"Failed to list or connect to any VISA resources: {e}")
        print(f"Retrying connection in 5 seconds...")
        time.sleep(reconnectDelay)  # Wait before retrying
    
    print("Failed to connect to the oscilloscope after multiple attempts.")
    return None

def reconnect_scope(scope, instrument_ids):
    """ Attempt to reconnect to the oscilloscope if the connection is lost. """
    print("Lost connection to the oscilloscope. Attempting to reconnect...")
    try:
        scope.close()  # Close existing connection if still open
    except Exception as e:
        print(f"Error closing existing connection: {e}")
    return connect_to_scope(instrument_ids)


# Connection process
scope = connect_to_scope(instrumentIds)
if scope is None:
    print("No known oscilloscopes were connected. Exiting.")
    exit(1)


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
        f":MATH:DEFINE {mathFunction}; LABEL {mathLabel}\n", # Labels the function and sets the calculation as Vrms/Irms
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


for command in commands:
    try:
        scope.write(command)
    except Exception as e:
        print(f"Failed to send command {command.strip()}: {e}")

print("Waiting for Trigger to be triggered")
print("Press Ctrl-C at any time to stop ...") ####### USER CAN STOP THE SCRIPT BY PRESSING 'Ctrl' AND 'C' ########

while True:
    triggerStatus = waitForTrigger(scope)
    #print(f"Trigger Status: {triggerStatus}")
    if triggerStatus == "TRIGGER":
        print("Trigger activated, starting acquisition...")
        break

with open(logfile, 'w', newline='') as csvfile:
    csvwriter = csv.writer(csvfile, delimiter=',')
    csvwriter.writerow(['Time', 'VRMS', 'IRMS', 'Freq', 'Phase', 'Impedance'])
    signal.signal(signal.SIGINT, signalHandler)
        
    startTime = time.time()
    
    while run and (time.time() - startTime) <= testTime:
        now = time.time() - startTime
        try:
            measurements = []
            for i in range(1, 6):
                query = f"MEASUREMENT:MEAS{i}:VALUE?"
                try:
                    response = scope.query(query).strip()  # <-- Inserted try-except for connection loss
                except (pyvisa.VisaIOError, pyvisa.VisaError) as e:
                    print(f"Connection lost: {e}")
                    scope = reconnect_scope(scope, instrumentIds)
                    if scope is None:
                        print("Failed to reconnect to the oscilloscope. Exiting.")
                        run = False
                        break
                    continue
                
                try:
                    if isinstance(response, bytes):
                        value = float(response.decode('utf-8'))
                    else:
                        value = float(response)
                    if value == 9.91e+37:  # NAN value from oscilloscope indicates measurement not ready
                        print("Measurement not ready, skipping ...")
                        time.sleep(0.1)  # Wait for 0.1s before retrying
                        continue
                    measurements.append(value)
                except ValueError:
                    print(f"Invalid response '{response}' from {query}, logging as NaN.")
                    value = float('nan')

            if len(measurements) == 5:
                print(f"{now:.6f}: Vrms: {measurements[0]} V, IRMS: {measurements[1]} A, "
                      f"Freq: {measurements[2]} Hz, Phase: {measurements[3]} deg, "
                      f"Impedance: {measurements[4]}")
                csvwriter.writerow([now] + measurements)
                csvfile.flush()  # Ensure data is written to disk

            time.sleep(0.01)
        except Exception as e:
            print(f"Error during measurement acquisition: {e}")

try:
    scope.write("ACQuire:STATE STOP\n")
    print("Acquisition stopped.")
except Exception as e:
    print(f"Error stopping acquisition: {e}")

scope.close()

def addColumnVOverI(inputFile, outputFile):
    with open(inputFile, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        rows = list(csvreader)

    if rows:
        rows[0].append("V/I")
        for i in range(1, len(rows)):
            try:
                voltage = float(rows[i][1])
                current = float(rows[i][2])
                vOverI = voltage / current if current != 0 else None
            except (ValueError, IndexError):
                vOverI = None
            rows[i].append(vOverI)
    try:
        with open(outputFile, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerows(rows)
    except Exception as e:
        print(f"Error writing to {outputFile}: {e}")

    print(f"Processed file saved as: {outputFile}")
