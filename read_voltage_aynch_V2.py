```python
import glob
import asyncio
from datetime import datetime
from smbus2 import SMBus


bus = SMBus(1)
address = 0x48

# Seconds between samples
sample_rate = 10

# Use a number to stop after that many samples
# Use None to run continuously
number_of_samples = None

# Choose: ph, ec, turbidity, temperature, or all
sensors = ["all"]

# Choose: read, cal_ph7, cal_ph4, or cal_ec
mode = "read"


# Add these values after calibration
ph7_cal_voltage = None
ph4_cal_voltage = None
ec_cal_factor = 1.0

# EC calibration solution
ec_standard_ppm = 707.0

# Number of readings used during calibration
cal_samples = 30
cal_delay = 0.2
cal_settle_time = 10


temp_files = glob.glob("/sys/bus/w1/devices/28-*/w1_slave")


async def read_adc(channel):

    config = 0x8183 | ((4 + channel) << 12)

    bus.write_i2c_block_data(
        address,
        1,
        [config >> 8, config & 0xFF]
    )

    await asyncio.sleep(0.02)

    data = bus.read_i2c_block_data(address, 0, 2)
    reading = (data[0] << 8) | data[1]

    if reading >= 32768:
        reading = reading - 65536

    voltage = reading * 6.144 / 32768

    return voltage


def read_temp():

    if len(temp_files) == 0:
        return None

    file = open(temp_files[0], "r")
    data = file.read()
    file.close()

    if "YES" not in data or "t=" not in data:
        return None

    temp = float(data.split("t=")[1]) / 1000

    return temp


def convert_ph(voltage):

    if ph7_cal_voltage is None or ph4_cal_voltage is None:
        return None

    if ph7_cal_voltage == ph4_cal_voltage:
        return None

    slope = (4.0 - 7.0) / (ph4_cal_voltage - ph7_cal_voltage)
    ph = 7.0 + slope * (voltage - ph7_cal_voltage)

    return ph


def calculate_tds(voltage, temperature, cal_factor):

    temp_adjustment = 1.0 + 0.02 * (temperature - 25.0)
    corrected_voltage = voltage / temp_adjustment

    tds = (
        133.42 * corrected_voltage**3
        - 255.86 * corrected_voltage**2
        + 857.39 * corrected_voltage
    ) * 0.5

    tds = tds * cal_factor

    if tds < 0:
        tds = 0

    return tds


async def average_adc(channel):

    readings = []

    for sample in range(cal_samples):

        voltage = await read_adc(channel)
        readings.append(voltage)

        print(
            "Calibration reading",
            sample + 1,
            ":",
            round(voltage, 4),
            "V"
        )

        await asyncio.sleep(cal_delay)

    average = sum(readings) / len(readings)

    return average


async def calibrate():

    print("Waiting for the sensor to settle...")
    await asyncio.sleep(cal_settle_time)

    if mode == "cal_ph7":

        print("Calibrating pH sensor with pH 7.00 solution")

        average_voltage = await average_adc(0)

        print("-----------------------")
        print("pH 7 calibration voltage:", round(average_voltage, 5), "V")
        print("Enter this value into ph7_cal_voltage")

    elif mode == "cal_ph4":

        print("Calibrating pH sensor with pH 4.00 solution")

        average_voltage = await average_adc(0)

        print("-----------------------")
        print("pH 4 calibration voltage:", round(average_voltage, 5), "V")
        print("Enter this value into ph4_cal_voltage")

    elif mode == "cal_ec":

        print("Calibrating EC estimate with 707 ppm solution")

        temperature = read_temp()

        if temperature is None:
            temperature = 25.0
            print("Temperature sensor not detected")
            print("Using 25 C")

        average_voltage = await average_adc(1)

        uncalibrated_tds = calculate_tds(
            average_voltage,
            temperature,
            1.0
        )

        if uncalibrated_tds <= 0:
            print("Calibration failed")
            return

        factor = ec_standard_ppm / uncalibrated_tds

        print("-----------------------")
        print("EC calibration voltage:", round(average_voltage, 5), "V")
        print("Temperature:", round(temperature, 2), "C")
        print("Uncalibrated TDS:", round(uncalibrated_tds, 2), "ppm")
        print("EC calibration factor:", round(factor, 6))
        print("Enter this value into ec_cal_factor")

    else:
        print("Calibration mode not recognized")


async def main():

    if mode != "read":
        await calibrate()
        return

    if sample_rate <= 0:
        print("Sample rate must be greater than zero")
        return

    if number_of_samples is not None and number_of_samples <= 0:
        print("Number of samples must be greater than zero")
        return

    sample_count = 0

    while number_of_samples is None or sample_count < number_of_samples:

        start_time = asyncio.get_running_loop().time()

        sample_count = sample_count + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("Sample:", sample_count)

        temp = None

        if (
            "all" in sensors
            or "temperature" in sensors
            or "ec" in sensors
        ):
            temp = read_temp()

        if "all" in sensors or "ph" in sensors:

            ph_voltage = await read_adc(0)
            ph = convert_ph(ph_voltage)

            if ph is None:
                print(
                    timestamp,
                    "- pH not calibrated:",
                    round(ph_voltage, 3),
                    "V"
                )
            else:
                print(
                    timestamp,
                    "- pH:",
                    round(ph, 2),
                    "- Voltage:",
                    round(ph_voltage, 3),
                    "V"
                )

        if "all" in sensors or "ec" in sensors:

            ec_voltage = await read_adc(1)

            if temp is None:
                ec_temperature = 25.0
            else:
                ec_temperature = temp

            tds = calculate_tds(
                ec_voltage,
                ec_temperature,
                ec_cal_factor
            )

            estimated_ec_us = tds * 2
            estimated_ec_ms = estimated_ec_us / 1000

            print(
                timestamp,
                "- Estimated EC:",
                round(estimated_ec_ms, 3),
                "mS/cm"
            )

            print(
                timestamp,
                "- TDS:",
                round(tds, 1),
                "ppm",
                "- Voltage:",
                round(ec_voltage, 3),
                "V"
            )

        if "all" in sensors or "turbidity" in sensors:

            turbidity_voltage = await read_adc(2)

            print(
                timestamp,
                "- Turbidity voltage:",
                round(turbidity_voltage, 3),
                "V"
            )

        if "all" in sensors or "temperature" in sensors:

            if temp is None:
                print(timestamp, "- Temperature sensor not detected")
            else:
                print(
                    timestamp,
                    "- Temperature:",
                    round(temp, 2),
                    "C"
                )

        print("-----------------------")

        if (
            number_of_samples is not None
            and sample_count >= number_of_samples
        ):
            break

        time_used = asyncio.get_running_loop().time() - start_time
        time_left = sample_rate - time_used

        if time_left > 0:
            await asyncio.sleep(time_left)

    print("Finished collecting", sample_count, "samples")


try:
    asyncio.run(main())

except KeyboardInterrupt:
    print("stopped")

finally:
    bus.close()
```
