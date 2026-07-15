import glob
import asyncio
#Used for ADS1115
from smbus2 import SMBus

#I2C bus 1 on the Raspberry Pi
bus = SMBus(1)

#I2C address
address = 0x48

#DS18B20 temperature sensors
temp_files = glob.glob("/sys/bus/w1/devices/28-*/w1_slave")

#Read ADC
async def read_adc(channel):

    #ADS1115
    #0x8183 sets ADS for single reading
    #selecting the which sensor we want
    config = 0x8183 | ((4 + channel) << 12)

    #configuration to ADS1115
    bus.write_i2c_block_data(address,1,[config >> 8, config & 0xFF])

    #wait for ads to finish reading
    await asyncio.sleep(0.02)

    #reads from the i2c bus
    data = bus.read_i2c_block_data(address, 0, 2)

    #combines the two bytes
    reading = (data[0] << 8) | data[1]

    #converts value if it is negative
    if reading >= 32768:
        reading = reading - 65536

    #value into voltage
    voltage = reading * 6.144 / 32768

    return voltage


# Read the DS18B20 temperature sensor
def read_temp():

    # Check if a temperature sensor was found
    if len(temp_files) == 0:
        return None

    # Open the temperature sensor file
    file = open(temp_files[0], "r")

    # Read the information in the file
    data = file.read()

    # Close the file
    file.close()

    # Check that the sensor reading was successful
    if "YES" not in data:
        return None

    # Get the temperature value after "t="
    temp = data.split("t=")[1]

    # Convert the temperature from thousandths of a degree to degrees Celsius
    temp = float(temp) / 1000

    # Send the temperature back to the main program
    return temp


# Main asynchronous program
async def main():

    while True:
        ph = await read_adc(0)
        ec = await read_adc(1)
        turbidity = await read_adc(2)
        temp = read_temp()

        print("pH voltage:", round(ph, 3), "V")
        print("EC voltage:", round(ec, 3), "V")
        print("Turbidity voltage:", round(turbidity, 3), "V")

        if temp is None:
            print("Temperature sensor not detected")
        else:
            print("Temperature:", round(temp, 2), "C")

        await asyncio.sleep(1)


# Try to keep taking readings
try:

    asyncio.run(main())

except KeyboardInterrupt:

    print("stopped")

finally:

    bus.close()
