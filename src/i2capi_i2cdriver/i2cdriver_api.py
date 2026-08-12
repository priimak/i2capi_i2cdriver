from bitstring import BitArray, Bits
from i2c_api import I2CLogger, I2CMaster, I2CMessage
from i2c_api.log import I2CTransactionElement
from i2cdriver import I2CDriver


class DummyI2CLogger(I2CLogger):
    def log_message(self, message: list[I2CTransactionElement]):
        pass


class I2CMasterI2CDriver(I2CMaster):
    def __init__(self, driver: I2CDriver, logger: I2CLogger | None = None) -> None:
        self.driver = driver
        self._pullup_codes = [
            "disabled",
            "2.2K",
            "4.3K",
            "1.5K",
            "4.7K",
            "1.5K",
            "2.2K",
            "1.1K",
        ]
        self._pullup_values = ["disabled", "4.7K", "4.3K", "2.2K", "1.5K", "1.1K"]
        self.__logger = DummyI2CLogger() if logger is None else logger

    def logger(self) -> I2CLogger:
        return self.__logger

    def write(
        self,
        address: int,
        data: Bits | str | int | list[int],
        num_bytes: int | None = None,
    ) -> bool:
        log_msg = []
        payload = I2CMaster.pad_payload(I2CMaster.mk_payload(data), num_bytes)
        try:
            log_msg.append(I2CMessage.START)
            log_msg.append(I2CMessage.DATA_MOSI(BitArray(f"uint:7={address}")))
            log_msg.append(I2CMessage.WRITE)
            if not self.driver.start(address, 0):
                log_msg.append(I2CMessage.NACK)
                return False
            log_msg.append(I2CMessage.ACK)
            log_msg.append(I2CMessage.DATA_MOSI(payload))
            if self.driver.write(payload.bytes):
                log_msg.append(I2CMessage.ACK)
                return True
            else:
                log_msg.append(I2CMessage.NACK)
                return False
        finally:
            self.driver.stop()
            log_msg.append(I2CMessage.STOP)
            self.__logger.log_message(log_msg)

    def read(self, address: int, num_bytes: int = 1) -> Bits | None:
        log_msg = []
        try:
            log_msg.append(I2CMessage.START)
            log_msg.append(I2CMessage.DATA_MOSI(BitArray(f"uint:7={address}")))
            log_msg.append(I2CMessage.READ)
            if not self.driver.start(address, 1):
                log_msg.append(I2CMessage.NACK)
                return None
            else:
                log_msg.append(I2CMessage.ACK)
                data_from_the_client = Bits(self.driver.read(num_bytes))
                log_msg.append(I2CMessage.DATA_MISO(data_from_the_client))
                return data_from_the_client
        finally:
            self.driver.stop()
            log_msg.append(I2CMessage.STOP)
            self.__logger.log_message(log_msg)

    def read_register(
        self, address: int, register: int, num_bytes: int = 1, use_restart: bool = False
    ) -> Bits | None:
        log_msg = []
        try:
            log_msg.append(I2CMessage.START)
            device_address_to_log = BitArray(f"uint:7={address}")
            log_msg.append(I2CMessage.DATA_MOSI(device_address_to_log))
            log_msg.append(I2CMessage.WRITE)
            if not self.driver.start(address, 0):
                log_msg.append(I2CMessage.NACK)
                return None

            log_msg.append(I2CMessage.ACK)
            payload = BitArray(f"uint:8={register}")
            log_msg.append(I2CMessage.DATA_MOSI(payload))
            if not self.driver.write(payload.bytes):
                log_msg.append(I2CMessage.NACK)
                return None
            log_msg.append(I2CMessage.ACK)
            if not use_restart:
                self.driver.stop()
                log_msg.append(I2CMessage.STOP)
                log_msg.append(I2CMessage.START)
            else:
                log_msg.append(I2CMessage.RESTART)

            log_msg.append(I2CMessage.DATA_MOSI(device_address_to_log))
            log_msg.append(I2CMessage.READ)
            if not self.driver.start(address, 1):
                log_msg.append(I2CMessage.NACK)
                return None
            else:
                log_msg.append(I2CMessage.ACK)
            data_from_the_client = Bits(self.driver.read(num_bytes))
            log_msg.append(I2CMessage.DATA_MISO(data_from_the_client))
            return data_from_the_client
        finally:
            self.driver.stop()
            log_msg.append(I2CMessage.STOP)
            self.__logger.log_message(log_msg)

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
            raise RuntimeError(
                "Invalid clock speed value. Only 100 and 400 are allowed for this device."
            )
