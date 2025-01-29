# -*- coding: utf-8 -*- 
"""
Python script to remotely control a Tektronix 3-Series MDO oscilloscope.
"""

# Standard libraries
import socket
import signal
import csv
import time
from datetime import datetime
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Constants
IP = "192.168.1.2"
#IP = "169.254.213.237"
PORT = 4000
INPUT_BUFFER = 2 * 1024
RUN = True  # The loop runs until the user presses Ctrl-C

def main():
    filename, casenum, peakC, offset_use, trackingPeriod, trackedDevice = file_naming()
    
    if filename is None:
        print("Filename generation failed. Exiting.")
        return
    
    folder_name = create_folder_for_files(filename)
    # Save the last filename used
    with open('last_filename.txt', 'w') as f:
        f.write(filename)
    
    create_file_if_not_exists(os.path.join(folder_name, filename))

    # Initialize the WebDriver once
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # Open the oscilloscope web interface
    driver.get('http://192.168.1.2:81')  # Assuming this is the oscilloscope web interface

    if offset_use:
        connect_and_acquire_with_offset(driver, os.path.join(folder_name, filename), casenum, peakC, trackingPeriod)
    else:
        connect_and_acquire_without_offset(driver, os.path.join(folder_name, filename), casenum, peakC, trackingPeriod)
    
    driver.quit()  # Quit the driver at the end
def file_naming():
    """Prompt user for input and generate a valid filename."""
    try:
        # Prompt for load type
        loadUse = input("Which Load is being Used?\nImpedance Load #2 - EQ072 (x)\tImpedance Load #1 - EQ075 (y)\tFrequency Load - EQ076 (z)\tActuator (a)\tOther (o): ").lower()
        if loadUse == 'x':
            loadUse = 'EQ072'
            casenum = "Case " + input("Enter Case Number: ")
        elif loadUse == 'y':
            loadUse = 'EQ075'
            casenum = "Case " + input("Enter Case Number: ")
        elif loadUse == 'z':
            loadUse = 'EQ076'
            casenum = "Case " + input("Enter Case Number: ")
        elif loadUse == 'a':
            loadUse = 'Actuator'
            casenum = "Case " + input("Enter Case Number: ")
        elif loadUse == 'o':
            loadUse = input("Enter Load Name: ")
            casenum = "Case " + input("Enter Case Number: ")
        else:
            raise ValueError("Invalid selection for load type.")
        
        # Prompt for peak current and date
        peakC = None
        now = datetime.now()
        date = now.strftime("%d-%m-%Y %H.%M")
        
        # Prompt for tracked device
        trackedDevice = input("Which Device is being Tracked?\nPiezoDrive (p)\tController (c)\tOther (o): ").lower()
        if trackedDevice == 'p':
            trackedDevice = "PiezoDrive"
            peakC = " @" + input("Enter PiezoDrive Peak Current: ") + 'mA'
        elif trackedDevice == 'c':
            trackedDevice = "Controller"
            mode = input("Active (a) or Boost (b): ").lower()
            if mode == 'a':
                peakC = ' 220mA'
            elif mode == 'b':
                peakC = ' 260mA'
            else:
                raise ValueError("Invalid mode selection.")
        elif trackedDevice == 'o':
            trackedDevice = input("Enter Device Name: ")
            peakC = " @" + input(f"Enter {trackedDevice}'s Peak Current in mA: ") + 'mA'
        else:
            raise ValueError("Invalid selection for tracked device.")
        
        # Prompt for offset
        offset_use = False
        offsetValue = None
        if trackedDevice == "PiezoDrive":
            offset_use = input("Will testing use Offset? (y/n): ").lower() == 'y'
            if offset_use:
                offsetValue = input("Enter Offset Value: ")
        elif trackedDevice == "Other":
            offset_use = input(f"Does {trackedDevice} use offset? (y/n): ").lower() == 'y'
            if offset_use:
                offsetValue = input("Enter Offset Value: ")

        offset = f"{trackedDevice} offset: {offsetValue} Degrees" if offset_use else ""

        # Prompt for tracking duration
        while True:
            try:
                trackingPeriod = int(input("Tracking duration in seconds: "))
                if trackingPeriod <= 0:
                    raise ValueError("Please enter a positive integer.")
                break
            except ValueError as e:
                print(f"Invalid input: {e}")

        # Construct and sanitize filename
        filename = f"{trackedDevice} {loadUse} {casenum} {peakC} {date} {offset}.csv"
        filename = re.sub(r'[\/:*?"<>|]', '-', filename)

        return filename, casenum, peakC, offset_use, trackingPeriod, trackedDevice
    except Exception as e:
        print(f"An error occurred: {e}")
        return None, None, None, None, None, None

def create_file_if_not_exists(filepath):
    """Create an empty file if it doesn't already exist."""
    if not os.path.exists(filepath):
        print(f"Creating file: {filepath}")
        open(filepath, 'w').close()
    else:
        print(f"File {filepath} already exists.")


def signal_handler(signum, frame):
    """Signal handler to stop the acquisition loop."""
    global RUN
    print(f"Signal {signal.strsignal(signum)} received ... stopping")
    RUN = False

def connect_and_acquire_with_offset(driver, filename, casenum, peakC, trackingPeriod):
    """Connect to oscilloscope and acquire data with offset."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to {IP}, port {PORT} ...")
    s.connect((IP, PORT))
    
    send_command(s, "*idn?")
    send_command(s, "ACQuire:STOPAfter RUNSTop")
    send_command(s, "CLEAR")
    send_command(s, "ACQuire:STATE RUN")
    
    with open(filename, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        offset_value = input("Enter offset value: ")
        csvwriter.writerow(['Time (s)', 'Case Number', 'Peak Current', 'Voltage (V RMS)', 'Current (A RMS)', 
                            'Frequency (Hz)', 'Phase (deg)', 'Math Function (Ohms)', 'Offset'])

        acquire_data_loop(driver, s, csvwriter, filename, casenum, peakC, offset_value, True, trackingPeriod)

    send_command(s, "ACQuire:STATE STOP")
    s.close()

def connect_and_acquire_without_offset(driver, filename, casenum, peakC, trackingPeriod):
    """Connect to oscilloscope and acquire data without offset."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to {IP}, port {PORT} ...")
    s.connect((IP, PORT))

    send_command(s, "*idn?")
    send_command(s, "ACQuire:STOPAfter RUNSTop")
    send_command(s, "CLEAR")
    send_command(s, "ACQuire:STATE RUN")

    with open(filename, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(['Time (s)', 'Case Number', 'Peak Current', 'Voltage (V RMS)', 'Current (A RMS)', 
                            'Frequency (Hz)', 'Phase (deg)', 'Math Function (Ohms)'])

        acquire_data_loop(driver, s, csvwriter, filename, casenum, peakC, None, False, trackingPeriod)

    send_command(s, "ACQuire:STATE STOP")
    s.close()

def send_command(s, command, expect_response=False):
    """Send a command to the oscilloscope and optionally return the response."""
    command += "\n"
    s.send(command.encode())
    if expect_response:
        return recv_data(s)
    return None

def recv_data(s):
    """Receive data from the socket."""
    try:
        data = s.recv(INPUT_BUFFER).decode().strip()
        return data
    except socket.error as e:
        print(f"Error receiving data: {e}")
        return None

def acquire_data_loop(driver, s, csvwriter, filename, casenum, peakC, offset_value, offset_enabled, trackingPeriod):

    """Loop to acquire data from the oscilloscope and write it to CSV."""
    signal.signal(signal.SIGINT, signal_handler)

    start_time = time.time()
    print("Waiting 5 seconds before starting recording...")
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    print("Recording started...")
    record_start_time = time.time()

    screenshot_counter = 1  # Track screenshot count

    folder_name = os.path.splitext(filename)[0].strip()
    pictures_folder = os.path.join(folder_name, "Pictures")  # Create a Pictures subdirectory

    try:
        if not os.path.exists(pictures_folder):
            os.makedirs(pictures_folder)
            print(f"Created folder: {pictures_folder}")
        else:
            print(f"Folder {pictures_folder} already exists.")
    except Exception as e:
        print(f"Failed to create folder {pictures_folder}: {e}")
        return  # Exit if folder creation fails

    while RUN and (time.time() - record_start_time < trackingPeriod):
        meas1, meas2, meas3, meas4, meas5 = fetch_measurements(s)
        now = time.time() - start_time

        # Inside acquire_data_loop, use offset_enabled to check the condition
        if offset_enabled:
            print(f"{now:.2f}: Voltage: {meas1} V RMS, Current: {meas2} A RMS, Frequency: {meas3} Hz, "
                f"Phase: {meas4} deg, Math Function: {meas5} Ohms, Offset: {offset_value}")
            csvwriter.writerow([now - 5, casenum, peakC, meas1, meas2, meas3, meas4, meas5, offset_value])
        else:
            print(f"{now:.2f}: Voltage: {meas1} V RMS, Current: {meas2} A RMS, Frequency: {meas3} Hz, "
                f"Phase: {meas4} deg, Math Function: {meas5} Ohms")
            csvwriter.writerow([now - 5, casenum, peakC, meas1, meas2, meas3, meas4, meas5])

        # Take screenshot with incremented filename
        timestamp = f"{now:.0f}s"

        screenshot_filename = os.path.join(pictures_folder, f'picture_{screenshot_counter}_TestTime={timestamp}.png')
        take_screenshot(driver, screenshot_filename) 
        screenshot_counter += 1

        time.sleep(1)

def fetch_measurements(s):
    """Fetch measurements from the oscilloscope."""
    try:
        meas1 = send_command(s, "MEASUrement:MEAS1:VALue?", expect_response=True)
        meas2 = send_command(s, "MEASUrement:MEAS2:VALue?", expect_response=True)
        meas3 = send_command(s, "MEASUrement:MEAS3:VALue?", expect_response=True)
        meas4 = send_command(s, "MEASUrement:MEAS4:VALue?", expect_response=True)
        meas5 = send_command(s, "MEASUrement:MEAS5:VALue?", expect_response=True)

        # Print raw measurement responses for debugging
        print(f"Raw Measurements: {meas1}, {meas2}, {meas3}, {meas4}, {meas5}")

        # Attempt to convert to float, handling possible conversion errors
        meas1 = float(meas1)
        meas2 = float(meas2)
        meas3 = float(meas3)
        meas4 = float(meas4)
        meas5 = float(meas5)

    except ValueError as e:
        print(f"Error converting measurement: {e}")
        print("Received values: ", meas1, meas2, meas3, meas4, meas5)
        # Handle the situation (e.g., return None, raise an exception, etc.)
        return None, None, None, None, None

    return meas1, meas2, meas3, meas4, meas5


def take_screenshot(driver, screenshot_filename):
    """Take a screenshot using the provided WebDriver and save it to the given filename."""
    try: 
        driver.save_screenshot(screenshot_filename)
        print(f"Screenshot saved as {screenshot_filename}")
    except Exception as e:
        print(f"Error taking screenshot: {e}")
    
def create_folder_for_files(filename):
    """Create a folder based on the filename (excluding the .csv extension)."""
    folder_name = os.path.splitext(filename)[0].strip()  # Remove the .csv extension
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        print(f"Created folder: {folder_name}")
    else:
        print(f"Folder {folder_name} already exists.")
    return folder_name


if __name__ == "__main__":
    main()
