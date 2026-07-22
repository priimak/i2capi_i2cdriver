from typing import Optional

from bitstring import Bits, BitArray
from i2c_api import I2CMaster
from i2cdriver import I2CDriver


class I2CMasterI2CDriver(I2CMaster):
    def __init__(self, driver: I2CDriver) -> None:
        self.driver = driver
        self._pullup_codes = ["disabled", "2.2K", "4.3K", "1.5K", "4.7K", "1.5K", "2.2K", "1.1K"]
        self._pullup_values = ["disabled", "4.7K", "4.3K", "2.2K", "1.5K", "1.1K"]

    def mk_payload(self, data: Bits | str | int | list[int]) -> BitArray:
        if isinstance(data, int):
            return BitArray(f"uint:8={data}")
        elif isinstance(data, list):
            acc = BitArray(0)
            for b in data:
                acc += BitArray(f"uint:8={b}")
            return acc
        elif isinstance(data, str) or isinstance(data, Bits):
            return BitArray(data)
        else:
            raise RuntimeError("Invalid payload type")

    def pad_payload(self, payload: BitArray, num_bytes: int | None = None) -> Bits:
        if num_bytes is None:
            if payload.len % 8 != 0:
                payload.prepend(BitArray(8 - payload.len % 8))
            else:
                return payload

        elif payload.len > num_bytes * 8:
            payload = payload[-(num_bytes * 8):]

        elif payload.len < num_bytes * 8:
            payload.prepend(BitArray(num_bytes * 8 - payload.len))

        return payload

    def write(self, address: int, data: Bits | str | int | list[int], num_bytes: int | None = None) -> bool:
        payload = self.pad_payload(self.mk_payload(data), num_bytes)
        try:
            if not self.driver.start(address, 0):
                return False
            if self.driver.write(payload.bytes):
                return True
            else:
                return False
        finally:
            self.driver.stop()

    def read(self, address: int, num_bytes: int = 1) -> Optional[Bits]:
        try:
            if not self.driver.start(address, 1):
                return None
            else:
                return Bits(self.driver.read(num_bytes))
        finally:
            self.driver.stop()

    def read_register(self, address: int, register: int, num_bytes: int = 1, use_restart: bool = False) \
            -> Optional[Bits]:
        try:
            if not self.driver.start(address, 0):
                return None

            payload = BitArray(f"uint:8={register}")
            if not self.driver.write(payload.bytes):
                return None
            if not use_restart:
                self.driver.stop()

            if not self.driver.start(address, 1):
                return None
            return Bits(self.driver.read(num_bytes))
        finally:
            self.driver.stop()

    def write_register(self, address: int, register: int, data: Bits | str | int | list[int],
                       num_bytes: int = 1) -> bool:
        payload = BitArray(f"uint:8={register}") + self.pad_payload(self.mk_payload(data), num_bytes)
        return self.write(address, payload)

    def scan(self) -> list[int]:
        return self.driver.scan(silent=True)

    def list_pullups(self) -> list[str]:
        return self._pullup_values

    def set_pullup(self, pullup_value: str) -> None:
        code = self._pullup_codes.index(pullup_value)
        self.driver.setpullups(code | code << 3)

    def get_pullup(self) -> str:
        return self._pullup_codes[self.driver.pullups & 7]

    def list_clk_speeds(self) -> list[int]:
        return [100, 400]

    def get_clk_speed(self) -> int:
        return self.driver.speed

    def set_clk_speed(self, speed: int) -> None:
        if speed in self.list_clk_speeds():
            self.driver.setspeed(speed)
        else:
            raise RuntimeError("Invalid clock speed value. Only 100 and 400 are allowed for this device.")
