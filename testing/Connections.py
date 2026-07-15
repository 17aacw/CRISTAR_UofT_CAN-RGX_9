#Varify that the Box is ready to use.
"""
LabControlSystem Hardware Test

Single-read diagnostic test for:
    - IvyLaser
    - BME280
    - BNO08X

"""

import time
import board

from laser_controller import IvyLaser

import adafruit_bme280.basic as adafruit_bme280

from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_ROTATION_VECTOR
)


print("=" * 60)
print("LAB CONTROLSYSTEM HARDWARE TEST")
print("=" * 60)


# ==========================================================
# I2C BUS
# ==========================================================

try:
    i2c = board.I2C()
    print("\n✓ I2C initialized")

except Exception as e:
    print(f"\n✗ I2C initialization failed: {e}")
    i2c = None


# ==========================================================
# BME280 TEST
# ==========================================================

if i2c:

    try:

        print("\n--- BME280 TEST ---")

        bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)

        print("✓ BME280 connected")

        print(
            f"Temperature : {bme280.temperature:.2f} °C"
        )

        print(
            f"Humidity    : {bme280.humidity:.2f} %"
        )

        print(
            f"Pressure    : {bme280.pressure:.2f} hPa"
        )


    except Exception as e:

        print(f"✗ BME280 failed: {e}")


# ==========================================================
# BNO08X TEST
# ==========================================================

if i2c:

    try:

        print("\n--- BNO08X TEST ---")

        bno = BNO08X_I2C(i2c)

        bno.enable_feature(BNO_REPORT_ACCELEROMETER)
        bno.enable_feature(BNO_REPORT_GYROSCOPE)
        bno.enable_feature(BNO_REPORT_MAGNETOMETER)
        bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)

        time.sleep(1)

        print("✓ BNO08X connected")

        accel = bno.acceleration
        gyro = bno.gyro
        mag = bno.magnetic
        quat = bno.quaternion


        print(
            f"Acceleration: "
            f"{accel[0]:.3f}, "
            f"{accel[1]:.3f}, "
            f"{accel[2]:.3f}"
        )

        print(
            f"Gyroscope: "
            f"{gyro[0]:.3f}, "
            f"{gyro[1]:.3f}, "
            f"{gyro[2]:.3f}"
        )

        print(
            f"Magnetic: "
            f"{mag[0]:.3f}, "
            f"{mag[1]:.3f}, "
            f"{mag[2]:.3f}"
        )

        print(
            f"Quaternion: "
            f"{quat[0]:.3f}, "
            f"{quat[1]:.3f}, "
            f"{quat[2]:.3f}, "
            f"{quat[3]:.3f}"
        )


    except Exception as e:

        print(f"✗ BNO08X failed: {e}")


# ==========================================================
# IVY LASER TEST
# ==========================================================

try:

    print("\n--- IVY LASER TEST ---")

    print("Creating laser object...")

    laser = IvyLaser()

    print("Connecting to laser...")

    laser.connect()

    print("✓ Laser connected")


    print("Initializing laser...")

    laser.initialize(
        timeout=600,
        stability_time=3.0
    )

    print("✓ Laser initialized")


    print("Reading laser status...")

    status = laser.get_status()

    print(f"Raw Status Code: {status}")


    if status == 16384:
        print("Status: OFF")

    elif status == 24576:
        print("Status: THERMALIZED")

    elif status == 24577:
        print("Status: ON")

    else:
        print("Status: UNKNOWN")


    laser.disconnect()

    print("✓ Laser disconnected")


except Exception as e:

    print(f"✗ Laser failed: {e}")


print("\n")
print("=" * 60)
print("HARDWARE TEST COMPLETE")
print("=" * 60)
