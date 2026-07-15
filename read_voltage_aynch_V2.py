
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
sensors = ["ph"]

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

    if len(lines) < 2:
        return None

    try:
        return float(lines[1].split("t=")[1]) / 1000

    except (IndexError, ValueError):
        return None


async def main():
    count = 0
    loop = asyncio.get_running_loop()
    next_sample = loop.time()

    while number_of_samples is None or count < number_of_samples:
        count += 1

        output = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]

        if sensor_on("ph"):
            voltage = await read_adc(0)
            output.append(f"pH voltage: {voltage:.3f} V")

        if sensor_on("ec"):
            voltage = await read_adc(1)
            output.append(f"EC voltage: {voltage:.3f} V")

        if sensor_on("turbidity"):
            voltage = await read_adc(2)
            output.append(f"Turbidity voltage: {voltage:.3f} V")

        if sensor_on("temperature"):
            temperature = read_temp()

            if temperature is None:
                output.append("Temperature: unavailable")
            else:
                output.append(f"Temperature: {temperature:.2f} C")

        print(" ".join(output))

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

