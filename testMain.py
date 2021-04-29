#!/usr/bin/env python3
# Name: Raiyan Nasim
# StudentID: 69632419
import RPi.GPIO as GPIO
from PCF8574 import PCF8574_GPIO
from Adafruit_LCD1602 import Adafruit_CharLCD
import Freenove_DHT as DHT
import threading
import smbus
import urllib.request
import codecs
import csv

import time
import datetime
from time import sleep, strftime
from datetime import datetime, date

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

#PINS
DHTpin = 11
LEDpin = 12
PIRpin = 13

dht = None

# CONSTANTS:
PF = 1.0 # This is the plant factor. 1.0 for lawn.  For shrubs ~ .3-.80
SF = 1500 # This is the area to be irrigated in square feet
IE = 0.75 # Irrigation efficiency.  (Sprinkler: ~75-80%, Drip irrigation systems ~90%)
WATER_DEBIT = 1020 # gallons/hour pump rating
#Gallons of Water per day (ET-station ) =  (ET0 x PF x SF x 0.62 ) / IE

#GLOBAL VARIABLES:

CIMIS_TEMPERATURE = 0.0
CIMIS_HUMIDITY = 0
CIMIS_ETO = 0.00
PUMP_STATUS = 0
#if PUMP_STATUS is 0 water pump is OFF
#if PUMP_STATUS is 1 water pump is ON
LAST_HUMIDITY = 0
CURRENT_AVG_TEMP = 0.0
CURRENT_AVG_HUMIDITY = 0
CURRENT_HOUR = 0
LAST_HOUR = 0
PRINTING_HOURLY_STATS = False
# Setup GPIO in/out


GPIO.setup(LEDpin, GPIO.OUT)    # set ledPin to OUTPUT mode
GPIO.setup(PIRpin, GPIO.IN)  # set sensorPin to INPUT mode
GPIO.setup(DHTpin, GPIO.IN)    # set ledPin to OUTPUT mode

def get_CIMIS_DATA():
    global CIMIS_ETO
    global CIMIS_HUMIDITY
    global CIMIS_TEMPERATURE

    ftp = urllib.request.urlopen("ftp://ftpcimis.water.ca.gov/pub2/hourly/hourly075.csv")
    csv_file = csv.reader(codecs.iterdecode(ftp,'utf-8'))
    for line in reversed(list(csv_file)):
        if (line[4] != "--" and line[14] != "--" and line[22] != "--"):
            CIMIS_ETO = line[4]
            CIMIS_HUMIDITY = line[14]
            CIMIS_TEMPERATURE = line[22]
            break;

def get_cpu_temp():     # get CPU temperature and store it into file "/sys/class/thermal/thermal_zone0/temp"
    tmp = open('/sys/class/thermal/thermal_zone0/temp')
    cpu = tmp.read()
    tmp.close()
    return '{:.2f}'.format( float(cpu)/1000 ) + ' C'

def get_time_now():     # get system time
    return datetime.now().strftime('    %H:%M:%S')

def get_local_temp():
    check = None
    while(check is not dht.DHTLIB_OK ):
        check = dht.readDHT11()
    temp = dht.temperature
    return temp

def get_local_humidity():
    global LAST_HUMIDITY
    check = None
    while(check is not dht.DHTLIB_OK):
        check = dht.readDHT11()
    humidity = dht.humidity
    if(humidity > 0 and humidity < 100):
        return humidity
    else:
        print("READ BAD HUMIDITY DATA. USING THE LAST VALID DATA!")
        return LAST_HUMIDITY


def hour_calculation_thread():
    global CIMIS_ETO
    global CIMIS_HUMIDITY
    global CIMIS_TEMPERATURE
    global dht
    global CURRENT_AVG_TEMP
    global CURRENT_AVG_HUMIDITY
    global CURRENT_HOUR
    global LAST_HOUR
    global PRINTING_HOURLY_STATS
    global PUMP_STATUS
    current_day = 0
    gallons_of_water_irrigated_today=[]
    adj_ETo_list = []
    no_adj_ETo_list = []
    mcp.output(3,1)     # turn on LCD backlight
    lcd.begin(16,2)     # set number of LCD lines and columns
    lcd.setCursor(0,1)
    text = "Welcome to AMS!"
    lcd.message(text)
    GPIO.output(LEDpin, GPIO.LOW)

    while True:
        if CURRENT_HOUR > 0 and (CURRENT_HOUR-LAST_HOUR) == 1:

            #print("TIMING: %d"%(CURRENT_HOUR-last_hour))
            start_time = time.time()
            print("-----------------%d hour has passed!------------------------\n"%(CURRENT_HOUR))
            print("Avg local temp:%.2f Avg local humidity:%.2f \n"%(CURRENT_AVG_TEMP, CURRENT_AVG_HUMIDITY))
            get_CIMIS_DATA()
            CIMIS_ETO = float(CIMIS_ETO)
            CIMIS_HUMIDITY = int(CIMIS_HUMIDITY)
            CIMIS_TEMPERATURE = (float(CIMIS_TEMPERATURE)-32) *(5/9)
            print("CIMIS_ETO: %.2f CIMIS_HUMIDITY: %d CIMIS_TEMPERATURE: %.2f \n"%(CIMIS_ETO, CIMIS_HUMIDITY, CIMIS_TEMPERATURE))
            #find the adjustment ratios
            temp_adj_ratio = CURRENT_AVG_TEMP/CIMIS_TEMPERATURE
            humid_adj_ratio = CURRENT_AVG_HUMIDITY/CIMIS_HUMIDITY

            if temp_adj_ratio > humid_adj_ratio:
                #if temp ratio is higher
                adjustedETO = CIMIS_ETO/(temp_adj_ratio)
            else:
                #if humid_adj_ratio is higher
                adjustedETO = CIMIS_ETO/(humid_adj_ratio)

            PRINTING_HOURLY_STATS = True
            lcd.setCursor(0,0)
            local_text = "adj ET0:%.2f Avg H:%d \n Local avg T:%.2fC"%(adjustedETO, CURRENT_AVG_HUMIDITY, CURRENT_AVG_TEMP)
            lcd.message(local_text)
            for x in range(0, len(local_text)):
                lcd.DisplayLeft()
                time.sleep(0.5)# duration of scrolling
            lcd.clear()
            time.sleep(0.5)
            lcd.setCursor(0,0)
            CIMIS_text = "CIMIS ET0:%.2f CIMIS RH:%d \n CIMIS Avg_Temp:%.2fC"%(CIMIS_ETO, CIMIS_HUMIDITY, CIMIS_TEMPERATURE)
            lcd.message(CIMIS_text)
            for x in range(0, len(CIMIS_text)):
                lcd.DisplayLeft()
                time.sleep(0.5)# duration of scrolling
            lcd.clear()
            PRINTING_HOURLY_STATS = False

            gallons_needed_to_irrigate_no_adj = (CIMIS_ETO * PF * SF * 0.62)/IE
            gallons_needed_to_irrigate_adj = (adjustedETO * PF * SF * 0.62)/IE

            #getting data for the 24 Hour Report
            gallons_of_water_irrigated_today.append(adjustedETO)
            adj_ETo_list.append(gallons_needed_to_irrigate_adj/float(24))
            no_adj_ETo_list.append(gallons_needed_to_irrigate_no_adj/float(24))

            #printing to LCD and Console
            PRINTING_HOURLY_STATS = True
            lcd.clear()
            lcd.setCursor(0,0)

            print("Amount of water needed to irrigate without adjustment: %.2f\n"%(gallons_needed_to_irrigate_no_adj/float(24)))
            print("Amount of water needed to irrigate with adjustment: %.2f\n"%(gallons_needed_to_irrigate_adj/float(24)))

            lcd.message("W/O adj H2O:%.2f\n"%(gallons_needed_to_irrigate_no_adj))
            lcd.message("W adj H2O:%.2f"%(gallons_needed_to_irrigate_adj))
            sleep(5)
            lcd.clear()
            if (gallons_needed_to_irrigate_no_adj-gallons_needed_to_irrigate_adj)>0:
                lcd.setCursor(0,0)
                lcd.message("H2O saved: \n%.2f gal"%(gallons_needed_to_irrigate_no_adj-gallons_needed_to_irrigate_adj))
                print("Amount of H2O saved: %.2f gal"%(gallons_needed_to_irrigate_no_adj-gallons_needed_to_irrigate_adj))
            else:
                lcd.setCursor(0,0)
                lcd.message("H2O lost: \n%.2f gal"%(gallons_needed_to_irrigate_adj-gallons_needed_to_irrigate_no_adj))
                print("Amount of H2O lost: %.2f gal"%(gallons_needed_to_irrigate_adj-gallons_needed_to_irrigate_no_adj))
            time.sleep(5)
            lcd.clear()
            PRINTING_HOURLY_STATS = False
            gallons_needed_per_hr = gallons_needed_to_irrigate_adj/float(24)
            time_needed_to_irrigate = gallons_needed_per_hr/WATER_DEBIT

            if time_needed_to_irrigate == 0:
                print("No need to irrigate ET0 is zero for hour %d"%(CURRENT_HOUR))
            elif time_needed_to_irrigate > 0:
                print("Turing pump ON for %.2f min"%(time_needed_to_irrigate*60))
                #PRINTING_HOURLY_STATS = True
                #lcd.clear()
                # Turn pump ON
                PUMP_STATUS = 1
                lcd.setCursor(0,1)
                lcd.message("Pump On:%.2f min."%(time_needed_to_irrigate*60))
                GPIO.output(LEDpin, GPIO.HIGH)
                sleep(time_needed_to_irrigate)
                # Turn Pump OFF


                GPIO.output(LEDpin, GPIO.LOW)
                print("----------------Turning Pump off ----------------------\n")
                PUMP_STATUS = 0
                lcd.clear()

            else:
                print("There is problem with time_needed_to_irrigate.\n")

            if CURRENT_HOUR == 24:
                #get # of gallons of water irrigated that day
                # and total adjusted ET for report
                current_day+=1
                f = open("24hrLog.txt", "a")
                print("Printing Daily report...\n")
                f.write("DAILY REPORT FOR THE DAY : \n")
                f.write("#################################################\n")
                f.write("Number of gallons of water irrigated today: \n")
                total_gal_irrigated_today = 0
                total_adj_ET_today = 0
                for i in range(0,len(gallons_of_water_irrigated_today),1):
                    f.write("Hour: %d     adj_ET0: %.2f     CIMIS: %.2f     LOCAL: %.2f\n"%(i+1, gallons_of_water_irrigated_today[i], adj_ETo_list[i], no_adj_ETo_list[i] ))
                    total_gal_irrigated_today += no_adj_ETo_list[i]
                    total_adj_ET_today += adj_ETo_list[i]
                f.write("Total number of gallons irrigated today (CIMIS): %.2f\n"%(total_gal_irrigated_today))
                f.write("Total number of gallons irrigated today (LOCAL): %.2f \n"%(total_adj_ET_today))
                f.close()
                print("Done printing daily report\n")
                CURRENT_HOUR = 0

            #print("Hour: %d     Gallons irrigated: %.2f     Adj. ET0: %.2f\n"%(CURRENT_HOUR, gallons_of_water_irrigated_today[CURRENT_HOUR], adj_ETo_list[CURRENT_HOUR] ))
            LAST_HOUR = CURRENT_HOUR


def loop():
    global dht

    global CURRENT_AVG_TEMP
    global CURRENT_AVG_HUMIDITY
    global LAST_HUMIDITY
    global CIMIS_ETO
    global CIMIS_HUMIDITY
    global CIMIS_TEMPERATURE
    global CURRENT_HOUR
    global LAST_HOUR
    global PRINTING_HOURLY_STATS
    #setting up DHT11 with the pin
    dht = DHT.DHT(DHTpin)   #creates the DHT Class object

    avg_local_temperature = 0
    avg_local_humidity = 0
    local_temp_read_num = 0
    local_humid_read_num = 0
    numMin = 0
    numHrs = 0

    mcp.output(3,1)     # turn on LCD backlight
    lcd.begin(16,2)     # set number of LCD lines and columns
    time_started = time.time()
    while(True):
        #lcd.clear()
        local_temp = get_local_temp()
        local_humidity = get_local_humidity()
        LAST_HUMIDITY = local_humidity
        #min_passed = time.time() - time_started

        for i in range (0,60,1):#change to 60
            time_taken_to_retrieve_data = time.time()
            local_temp = get_local_temp()
            #if get_local_humidity() < 100:
            local_humidity = get_local_humidity()
            LAST_HUMIDITY = local_humidity
            avg_local_temperature += local_temp
            avg_local_humidity += local_humidity
            lcd.setCursor(0,0)  # set cursor position

            print("Data #" + str(i) + ": Temp:" + str(local_temp) + " Humid:" + str(local_humidity) + "\n")
            if(PRINTING_HOURLY_STATS == False):
                lcd.message(" T:%.2f H:%.1f\n"%(local_temp, local_humidity))
                #lcd.message('TEMP:' + str(local_temp) + 'HUM:'+ str(local_humidity)+'\n')
                #lcd.message(get_time_now())
            time_taken_to_retrieve_data = time.time() - time_taken_to_retrieve_data
            print( "Time passed : %.2f min\n"%((time.time()-time_started)/60))
            if i != 59:
                #debug
                time.sleep(1)
                #time.sleep(60 - time_taken_to_retrieve_data) #(60s - time it takes to get the data)sleep for a min

        avg_local_temperature = avg_local_temperature/60 #change to 60
        CURRENT_AVG_TEMP = avg_local_temperature
        avg_local_humidity = avg_local_humidity/60 #change to 60
        CURRENT_AVG_HUMIDITY = avg_local_humidity
        LAST_HOUR = CURRENT_HOUR
        CURRENT_HOUR += 1

def destroy():
    lcd.clear()
    GPIO.output(LEDpin, GPIO.LOW)
    GPIO.cleanup()

PCF8574_address = 0x27  # I2C address of the PCF8574 chip.
PCF8574A_address = 0x3F  # I2C address of the PCF8574A chip.
# Create PCF8574 GPIO adapter.
try:
    mcp = PCF8574_GPIO(PCF8574_address)
except:
    try:
        mcp = PCF8574_GPIO(PCF8574A_address)
    except:
        print ('I2C Address Error !')
        exit(1)
# Create LCD, passing in MCP GPIO adapter.
lcd = Adafruit_CharLCD(pin_rs=0, pin_e=2, pins_db=[4,5,6,7], GPIO=mcp)

if __name__ == '__main__':
    t = None
    print ('Program is starting ... ')
    try:
        t = threading.Thread(target = hour_calculation_thread)
        t.daemon = True
        t.start()

        loop()

        t.join()
    except KeyboardInterrupt:
        destroy()