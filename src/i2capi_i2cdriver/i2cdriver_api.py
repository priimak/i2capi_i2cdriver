from bitstring import BitArray, Bits
from i2c_api import I2CLogger, I2CMaster, I2CMessage, RegisterAddress
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
        try:
            return self.__write(
                address,
                data=data,
                num_bytes=num_bytes,
                log_msg=log_msg,
                end_with_stop=True,
                start_with_restart=False,
            )
        finally:
            self.__logger.log_message(log_msg)

    def __write(
        self,
        address: int,
        *,
        data: Bits | str | int | list[int],
        log_msg: list[I2CTransactionElement],
        num_bytes: int | None,
        end_with_stop: bool,
        start_with_restart: bool,
    ) -> bool:
        payload = I2CMaster.pad_payload(I2CMaster.mk_payload(data), num_bytes)
        try:
            if start_with_restart:
                log_msg.append(I2CMessage.RESTART)
            else:
                log_msg.append(I2CMessage.START)

            log_msg.append(I2CMessage.DATA_MOSI(BitArray(f"uint:7={address}")))
            log_msg.append(I2CMessage.WRITE)
            if not self.driver.start(address, 0):
                log_msg.append(I2CMessage.NACK)
                return False
            log_msg.append(I2CMessage.ACK)

            bdata = [BitArray(f"uint:8={x}") for x in payload.tobytes()]
            if self.driver.write(payload.bytes):
                for data in bdata:
                    log_msg.append(I2CMessage.DATA_MOSI(data))
                    log_msg.append(I2CMessage.ACK)
                return True
            else:
                log_msg.append(I2CMessage.DATA_MOSI(bdata[0]))
                log_msg.append(I2CMessage.NACK)
                return False
        finally:
            if end_with_stop:
                self.driver.stop()
                log_msg.append(I2CMessage.STOP)

    def read(self, address: int, num_bytes: int = 1) -> Bits | None:
        log_msg = []
        try:
            return self.__read(
                address,
                num_bytes=num_bytes,
                end_with_stop=True,
                log_msg=log_msg,
                start_with_restart=False,
            )
        finally:
            self.__logger.log_message(log_msg)

    def __read(
        self,
        address: int,
        *,
        num_bytes: int,
        log_msg: list[I2CTransactionElement],
        end_with_stop: bool,
        start_with_restart: bool,
    ) -> Bits | None:
        try:
            if start_with_restart:
                log_msg.append(I2CMessage.RESTART)
            else:
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
                log_msg.append(I2CMessage.ACK)
                return data_from_the_client
        finally:
            if end_with_stop:
                self.driver.stop()
                log_msg.append(I2CMessage.STOP)

    def write_register(
        self,
        address: int,
        register: RegisterAddress,
        data: Bits | str | int | list[int],
        num_bytes: int | None = 1,
        read_back: bool = False,
        use_restart: bool = True,
    ) -> Bits | None:
        log_msg = []
        try:
            register_value = I2CMaster.pad_payload(
                I2CMaster.mk_payload(data), num_bytes
            )
            value_num_bytes = int(register_value.len / 8)
            self.__write(
                address,
                data=BitArray(
                    f"uint:{8 * register.bus_width_in_bytes}={register.address}"
                )
                + register_value,
                log_msg=log_msg,
                num_bytes=(value_num_bytes + register.bus_width_in_bytes),
                end_with_stop=(not read_back or not use_restart),
                start_with_restart=False,
            )
            if not read_back:
                return register_value
            else:  # read it back
                write_success = self.__write(
                    address,
                    data=BitArray(
                        f"uint:{8 * register.bus_width_in_bytes}={register.address}"
                    ),
                    log_msg=log_msg,
                    num_bytes=1,
                    end_with_stop=(not use_restart),
                    start_with_restart=use_restart,
                )
                if write_success:
                    return self.__read(
                        address,
                        num_bytes=value_num_bytes,
                        log_msg=log_msg,
                        end_with_stop=True,
                        start_with_restart=use_restart,
                    )
                else:
                    return None
        finally:
            self.__logger.log_message(log_msg)

    def read_register(
        self,
        address: int,
        register: RegisterAddress,
        num_bytes: int = 1,
        use_restart: bool = False,
    ) -> Bits | None:
        log_msg = []
        try:
            write_success = self.__write(
                address,
                data=BitArray(
                    f"uint:{8 * register.bus_width_in_bytes}={register.address}"
                ),
                log_msg=log_msg,
                num_bytes=register.bus_width_in_bytes,
                end_with_stop=(not use_restart),
                start_with_restart=False,
            )
            if write_success:
                return self.__read(
                    address,
                    num_bytes=num_bytes,
                    log_msg=log_msg,
                    end_with_stop=True,
                    start_with_restart=use_restart,
                )
            else:
                return None
        finally:
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
