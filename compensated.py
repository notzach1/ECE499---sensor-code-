import glob
import asyncio
from datetime import datetime
from smbus2 import SMBus


bus = SMBus(1)
address = 0x48

# Seconds between readings
sample_rate = 5

# Use a number, or None to run continuously
number_of_samples = 20

# Choose: ph, ec, turbidity, temperature, or all
sensors = ["ec"]

# Choose: normal, test_ph, or test_ec
mode = "test_ec"

# pH calibration averages
ph4_average = 0.58697
ph7_average = 2.07491

# Temperature when the pH sensor was calibrated
ph_calibration_temperature = 25.0

# Conductivity calibration factor
ec_calibration_factor = 1.37202

temp_files = glob.glob("/sys/bus/w1/devices/28-*/w1_slave")


def sensor_on(name):
    return "all" in sensors or name in sensors


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
        reading -= 65536

    return reading * 6.144 / 32768


def read_temp():
    if not temp_files:
        return None

    with open(temp_files[0], "r") as file:
        lines = file.read().splitlines()

    try:
        return float(lines[1].split("t=")[1]) / 1000

    except (IndexError, ValueError):
        return None


def calculate_ph(voltage):
    slope = (7.0 - 4.0) / (ph7_average - ph4_average)

    return 4.0 + slope * (voltage - ph4_average)


def compensate_ph(ph, temperature):
    calibration_kelvin = ph_calibration_temperature + 273.15
    measurement_kelvin = temperature + 273.15

    return 7.0 + (ph - 7.0) * (
        calibration_kelvin / measurement_kelvin
    )


def calculate_ec(voltage, temperature, compensated):
    if compensated:
        voltage = voltage / (
            1 + 0.02 * (temperature - 25.0)
        )

    tds = (
        133.42 * voltage**3
        - 255.86 * voltage**2
        + 857.39 * voltage
    ) * 0.5

    tds *= ec_calibration_factor

    return max(0, tds * 2 / 1000)


async def normal_reading(timestamp, temperature):
    output = [timestamp]
    temperature_used = temperature or 25.0

    if sensor_on("ph"):
        voltage = await read_adc(0)
        ph = calculate_ph(voltage)
        ph = compensate_ph(ph, temperature_used)

        output.append(f"pH: {ph:.2f}")

    if sensor_on("ec"):
        voltage = await read_adc(1)
        ec = calculate_ec(
            voltage,
            temperature_used,
            True
        )

        output.append(f"Estimated EC: {ec:.3f} mS/cm")

    if sensor_on("turbidity"):
        voltage = await read_adc(2)

        output.append(
            f"Turbidity voltage: {voltage:.3f} V"
        )

    if sensor_on("temperature"):
        if temperature is None:
            output.append("Temperature: unavailable")
        else:
            output.append(
                f"Temperature: {temperature:.2f} C"
            )

    return output


async def ph_test(timestamp, temperature):
    output = [timestamp]
    temperature_used = temperature or 25.0

    voltage = await read_adc(0)
    regular_ph = calculate_ph(voltage)
    compensated_ph = compensate_ph(
        regular_ph,
        temperature_used
    )

    output.append(f"pH regular: {regular_ph:.2f}")
    output.append(
        f"pH compensated: {compensated_ph:.2f}"
    )

    if temperature is None:
        output.append("Temperature: unavailable")
    else:
        output.append(f"Temperature: {temperature:.2f} C")

    return output


async def ec_test(timestamp, temperature):
    output = [timestamp]
    temperature_used = temperature or 25.0

    voltage = await read_adc(1)

    regular_ec = calculate_ec(
        voltage,
        temperature_used,
        False
    )

    compensated_ec = calculate_ec(
        voltage,
        temperature_used,
        True
    )

    output.append(
        f"EC regular: {regular_ec:.3f} mS/cm"
    )

    output.append(
        f"EC compensated: {compensated_ec:.3f} mS/cm"
    )

    if temperature is None:
        output.append("Temperature: unavailable")
    else:
        output.append(f"Temperature: {temperature:.2f} C")

    return output


async def main():
    count = 0
    loop = asyncio.get_running_loop()
    next_sample = loop.time()

    while number_of_samples is None or count < number_of_samples:
        count += 1

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        temperature = read_temp()

        if mode == "test_ph":
            output = await ph_test(
                timestamp,
                temperature
            )

        elif mode == "test_ec":
            output = await ec_test(
                timestamp,
                temperature
            )

        else:
            output = await normal_reading(
                timestamp,
                temperature
            )

        print(", ".join(output))

        if number_of_samples is not None and count >= number_of_samples:
            break

        next_sample += sample_rate
        wait_time = next_sample - loop.time()

        if wait_time > 0:
            await asyncio.sleep(wait_time)


try:
    asyncio.run(main())

except KeyboardInterrupt:
    pass

finally:
    bus.close()
