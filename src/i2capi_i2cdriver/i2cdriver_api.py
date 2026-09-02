from functools import partial, reduce
from typing import override

from bitstring import BitArray, Bits
from i2c_api import I2CError, I2CLogger, I2CMaster, I2CMessage, RegisterAddress
from i2c_api.commands import Address, Data, P, Read, S, Sr, W
from i2c_api.language import I2CTransaction
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
        if address < 0:
            raise I2CError("Invalid i2c device address")

        payload = I2CMaster.mk_payload(data, num_bytes)
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
        if address < 0:
            raise I2CError("Invalid i2c device address")

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
                bdata = [
                    BitArray(f"uint:8={x}") for x in data_from_the_client.tobytes()
                ]
                for data in bdata:
                    log_msg.append(I2CMessage.DATA_MISO(data))
                    log_msg.append(I2CMessage.ACK)
                return data_from_the_client
        finally:
            if end_with_stop:
                self.driver.stop()
                log_msg.append(I2CMessage.STOP)

    @override
    def _exec(self, transaction: I2CTransaction) -> tuple[list[list[BitArray]], bool]:
        calls = []
        data_out = []
        data_rsp = []
        nack = []
        stop_called = []
        f = None

        def read(num_bytes: int) -> None:
            data_from_the_client = Bits(self.driver.read(num_bytes))
            bdata = [BitArray(f"uint:8={x}") for x in data_from_the_client.tobytes()]
            data_rsp.append(bdata)

        def start(address: int, write_flag: int) -> None:
            if not self.driver.start(address, write_flag):
                nack.append(True)

        def write(data_bytes: bytes) -> None:
            if not self.driver.write(data_bytes):
                nack.append(True)

        def build_write_call():
            if data_out != []:
                wdata = reduce(
                    lambda acc, b: acc + b,
                    [BitArray(f"uint:8={d}") for d in data_out],
                    BitArray(),
                )
                calls.append(partial(write, wdata.bytes))
                data_out.clear()

        def stop():
            stop_called.append(True)
            self.driver.stop()

        for cmd in transaction._i2c_commands:
            if nack != []:
                break
            match cmd:
                case S():
                    f = partial(start)
                case Address(address):
                    f = partial(f, address)
                case W():
                    f = partial(f, 0)
                    calls.append(f)
                    f = None
                case Read(num_bytes):
                    f = partial(f, 1)
                    calls.append(f)
                    f = None
                    calls.append(partial(read, num_bytes))
                case Sr():
                    build_write_call()
                    f = partial(start)
                case P():
                    build_write_call()
                    calls.append(stop)
                case Data(data):
                    data_out.append(data)

        try:
            for i, c in enumerate(calls):
                if nack == []:
                    c()
                else:
                    break

            return [[c.uint for c in d] for d in data_rsp], (nack == [])
        finally:
            if stop_called != []:
                self.driver.stop()

    @override
    def write_register(
        self,
        address: int,
        register: RegisterAddress,
        data: Bits | str | int | list[int],
        num_bytes: int | None = None,
        read_back: bool = False,
        use_restart: bool = True,
    ) -> Bits | None:
        if address < 0:
            raise I2CError("Invalid i2c device address")

        log_msg = []
        try:
            register_value = I2CMaster.mk_payload(data, num_bytes)
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
        if address < 0:
            raise I2CError("Invalid i2c device address")

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
        if pullup_value in self._pullup_values:
            code = self._pullup_codes.index(pullup_value)
            self.driver.setpullups(code | code << 3)
        else:
            raise I2CError("Invalid pullup resistor value.")

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
            raise I2CError(
                "Invalid clock speed value. Only 100 and 400 are allowed for this device."
            )
