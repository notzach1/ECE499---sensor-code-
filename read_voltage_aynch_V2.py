```python
import glob
import asyncio
from datetime import datetime
from smbus2 import SMBus


bus = SMBus(1)
address = 0x48

# Seconds between readings
sample_rate = 10

# Use a number, or None to run continuously
number_of_samples = 30

# Choose: ph, ec, turbidity, temperature, or all
sensors = ["all"]

# Choose: read, calibrate_ph, or calibrate_ec
mode = "read"

# Enter these after pH calibration
ph7_cal_voltage = 0.0
ph4_cal_voltage = 0.0

# Enter this after EC calibration
ec_cal_factor = 1.0

calibration_samples = 30
calibration_delay = 0.2
ec_standard_ppm = 707.0

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

    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        return None

    try:
        return float(lines[1].split("t=")[1]) / 1000
    except (IndexError, ValueError):
        return None


def get_ph(voltage):
    slope = (4.0 - 7.0) / (ph4_cal_voltage - ph7_cal_voltage)

    return 7.0 + slope * (voltage - ph7_cal_voltage)


def get_tds(voltage, temperature, factor):
    corrected_voltage = voltage / (1 + 0.02 * (temperature - 25))

    tds = (
        133.42 * corrected_voltage**3
        - 255.86 * corrected_voltage**2
        + 857.39 * corrected_voltage
    ) * 0.5

    return max(0, tds * factor)


async def average_voltage(channel):
    total = 0

    for _ in range(calibration_samples):
        total += await read_adc(channel)
        await asyncio.sleep(calibration_delay)

    return total / calibration_samples


async def calibrate():
    if mode == "calibrate_ph":
        value = await average_voltage(0)
        print(f"{value:.5f}")

    elif mode == "calibrate_ec":
        temperature = read_temp() or 25.0
        voltage = await average_voltage(1)
        raw_tds = get_tds(voltage, temperature, 1.0)
        factor = ec_standard_ppm / raw_tds

        print(f"{factor:.6f}")


async def collect_data():
    count = 0
    loop = asyncio.get_running_loop()
    next_sample = loop.time()

    while number_of_samples is None or count < number_of_samples:
        count += 1

        output = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]

        temperature = None

        if sensor_on("temperature") or sensor_on("ec"):
            temperature = read_temp()

        if sensor_on("ph"):
            voltage = await read_adc(0)

            if ph7_cal_voltage > 0 and ph4_cal_voltage > 0:
                output.append(f"pH: {get_ph(voltage):.2f}")
            else:
                output.append(f"pH voltage: {voltage:.3f} V")

        if sensor_on("ec"):
            voltage = await read_adc(1)
            tds = get_tds(
                voltage,
                temperature or 25.0,
                ec_cal_factor
            )

            estimated_ec = tds * 2 / 1000

            output.append(
                f"Estimated EC: {estimated_ec:.3f} mS/cm"
            )

            output.append(
                f"TDS: {tds:.1f} ppm"
            )

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

        print(
            "\n".join(output)
            + "\n------------------------------"
        )

        if number_of_samples is not None and count >= number_of_samples:
            break

        next_sample += sample_rate
        wait_time = next_sample - loop.time()

        if wait_time > 0:
            await asyncio.sleep(wait_time)


async def main():
    if mode == "read":
        await collect_data()
    else:
        await calibrate()


try:
    asyncio.run(main())

except KeyboardInterrupt:
    pass

finally:
    bus.close()
```

::: 
