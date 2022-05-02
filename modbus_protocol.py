#!/usr/bin/python3.10
"""
Simple Modbus testing script for Circuit Breakers
"""
import argparse
import socket
import uuid
from sys import exit as sys_exit
from datetime import datetime
from time import sleep
import yaml
from pyModbusTCP.client import ModbusClient as modbus_client
from pymodbus.client.sync import ModbusTcpClient as modbus_client_custom
from pymodbus.mei_message import ReadDeviceInformationRequest
from addons import generate_test_report_json
from addons import generate_test_report_html
from addons import write_test_results_2_db


# Global Variables
__TIME_FORMAT__ = '%Y-%m-%d %H:%M:%S'
# Default values for modbus connection 
__DEFAULT_DEVICE_ADDRESS__ = "158.193.241.254"
__DEFAULT_DEVICE_PORT__ = 502
__DEFAULT_DEVICE_UNIT_ID__ = 255
# Global variable for test configuration
__TEST_CONFIGURATION__ = {}
# Communication timeouts
__WRITE_TIMEOUT__ = 0.5
__READ_TIMEOUT__ = 0.1
# Measurement timeouts
__STEP_TIMEOUT__ = 2
__PROBE_OFFSET__ = 2
__PROBE_COUNT__ = 10
# Print timeouts
__PRINT_TIMEOUT__ = 0.5


def normalize_integer_value(measurement_value: int) -> int:
    """
    Returns signed integer values
    :param measurement_value: unsigned int
    :return: signed int
    """
    if measurement_value == 32768:
        return 0
    if measurement_value > 32768:
        return measurement_value - 65536
    return measurement_value


def to_bool(bool_value: str) -> int:
    """
    Returns Bool equivalent in INT form
    :param bool_value: bool
    :return: int
    """
    if bool_value:
        return 1
    return 0


def load_test_configuration(file: str) -> None:
    """
    Loads config data to global variable
    :param file: Path to config file
    :return: None
    """
    global __TEST_CONFIGURATION__
    # Loads config file to global variable
    try:
        __TEST_CONFIGURATION__ = yaml.safe_load(open(file, 'r', encoding="utf-8"))
    except FileNotFoundError:
        print("Configuration file not found. Check config file.")
        exit(2)


def connection_test(address: str = __DEFAULT_DEVICE_ADDRESS__, port: int = __DEFAULT_DEVICE_PORT__) -> bool:
    """
    Simple socket test, checks if port is open
    :param address: IPv4 address
    :param port: Port
    :return: Result of test
    """
    # Creates socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Connects socket to given IP/port
    result = sock.connect_ex((address, port))
    # Closes socket
    sock.close()
    # Compares result
    if result == 0:
        print("Connection successful! Starting tests:")
        return True
    return False


def send_init_sequence(modbus_connection: modbus_client) -> bool:
    """
    Sends init sequence for remote control testing
    :param modbus_connection: Connection object
    :return: Status of write
    """
    for key in __TEST_CONFIGURATION__['init_sequence']:
        # Sends init sequence part
        status = modbus_connection.write_single_register(__TEST_CONFIGURATION__['init_sequence'][key]['address_dec'],
                                                         __TEST_CONFIGURATION__['init_sequence'][key]['data'])
        # Checks if sequence successfully writen
        if to_bool(status) == __TEST_CONFIGURATION__['init_sequence'][key]['pass_msg']:
            __TEST_CONFIGURATION__['init_sequence'][key]['status'] = to_bool(status)
        else:
            __TEST_CONFIGURATION__['init_sequence'][key]['status'] = to_bool(status)
        sleep(__WRITE_TIMEOUT__)
    return __TEST_CONFIGURATION__['init_sequence']


def send_password(modbus_connection: modbus_client) -> bool:
    """
    Writes password to specified registers
    :param modbus_connection: Connection object
    :return: Status of write
    """
    # Writes all keys in login section of the config file
    for key in __TEST_CONFIGURATION__['login']:
        # Sends passwd part
        status = modbus_connection.write_single_register(__TEST_CONFIGURATION__['login'][key]['address_dec'],
                                                         __TEST_CONFIGURATION__['login'][key]['data'])
        # Checks if passwd successfully writen
        if to_bool(status) == __TEST_CONFIGURATION__['login'][key]['pass_msg']:
            __TEST_CONFIGURATION__['login'][key]['status'] = to_bool(status)
        else:
            __TEST_CONFIGURATION__['login'][key]['status'] = to_bool(status)
        sleep(__WRITE_TIMEOUT__)
    return __TEST_CONFIGURATION__['login']


def device_connection(device_address: str = __DEFAULT_DEVICE_ADDRESS__, device_port: int = __DEFAULT_DEVICE_PORT__) \
        -> modbus_client:
    """
    Base connetion method for modbus devices over TCP
    :param device_address: IPv4 address of the TCP Modbus device
    :param device_port: Port for modbus communication, default 502
    :return: Connection object
    """
    # Creates object of ModbusClient
    connection = modbus_client(host=device_address, port=device_port, timeout=2, auto_open=True, auto_close=False,
                               unit_id=__DEFAULT_DEVICE_UNIT_ID__)
    # Tries to open connection via TCP
    connection.open()
    # Checks if connection is open, if true returns connection object, else exit with code 2 and a message
    try:
        if not connection.is_open:
            raise ConnectionError
    except ConnectionError:
        print("Connection problem, check device address!")
        sys_exit(2)
    return connection


def read_device_id_information(device_address: str = __DEFAULT_DEVICE_ADDRESS__,
                               device_port: int = __DEFAULT_DEVICE_PORT__) -> list:
    """
    Read Device Information using custom ReadDeviceInformationRequest
    :param device_address: IPv4 address of the Modbus device
    :param device_port: Port for modbus communication, default 502
    :return: Device Information
    """
    # Response data initialisation
    response_data = []
    # Creates connection to Device
    modbus_connection = modbus_client_custom(host=device_address, port=device_port)
    # Creates request body using ReadDeviceInformationRequest
    request = ReadDeviceInformationRequest(unit=__DEFAULT_DEVICE_UNIT_ID__)
    # Execute request
    response = modbus_connection.execute(request)
    # Readout data from response and store in response_data
    for key, value in response.information.items():
        response_data.append(str(value).split("'")[1])
    # Returns data from device
    return response_data


def remote_control_test(modbus_connection: modbus_client) -> dict:
    """
    Remote control test of the Device
    :param modbus_connection: Connection object
    :return: Status data
    """
    remote_control_status = {}
    remote_control_status.update(send_init_sequence(modbus_connection))
    print("-> Running Device Control Test Sequence:")
    # OFF motor control test
    remote_control_status.update(send_password(modbus_connection))
    print("   Sending OFF to motor control... ", end='')
    # Writes instruction
    modbus_connection.write_single_register(
        __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']['address_dec'],
        __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']['data'])
    # Reads status
    status = modbus_connection.read_holding_registers(
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['address_dec'],
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['count'])
    # Compare status with defined value
    if status[0] == __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']['pass_msg']:
        print("Pass")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']['status'] = 1
    else:
        print("Fail")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']['status'] = 0
    remote_control_status.update({'t_off_c_break': __TEST_CONFIGURATION__['remote_control_sequence']['t_off_c_break']})
    # ON motor control test
    send_password(modbus_connection)
    sleep(__STEP_TIMEOUT__)
    print("   Sending ON to motor control... ", end='')
    modbus_connection.write_single_register(
        __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']['address_dec'],
        __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']['data'])
    status = modbus_connection.read_holding_registers(
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['address_dec'],
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['count'])
    if status[0] == __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']['pass_msg']:
        print("Pass")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']['status'] = 1
    else:
        print("Fail")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']['status'] = 0
    remote_control_status.update({'t_on_c_break': __TEST_CONFIGURATION__['remote_control_sequence']['t_on_c_break']})
    # RESET motor control test
    send_password(modbus_connection)
    sleep(__STEP_TIMEOUT__)
    print("   Sending RESET to motor control... ", end='')
    modbus_connection.write_single_register(
        __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']['address_dec'],
        __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']['data'])
    status = modbus_connection.read_holding_registers(
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['address_dec'],
        __TEST_CONFIGURATION__['device_info']['get_dev_status']['count'])
    if status[0] == __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']['pass_msg']:
        print("Pass")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']['status'] = 1
    else:
        print("Fail")
        __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']['status'] = 0
    remote_control_status.update(
        {'t_reset_c_break': __TEST_CONFIGURATION__['remote_control_sequence']['t_reset_c_break']})

    print("   Done!")
    return remote_control_status


def device_information_read_test(modbus_connection: modbus_client) -> bool:
    """
    Device information read test
    :param modbus_connection: Connection object
    :return: device information
    """
    device_info = {}
    print("-> Running Information Read Test:")
    try:
        print("   Read Device Identification ... ", end='')
        data = read_device_id_information(modbus_connection.host, modbus_connection.port)
        __TEST_CONFIGURATION__['device_id']['reading'] = data
        sleep(__PRINT_TIMEOUT__)
        print(data, " Pass")
        device_info.update({'device_id': __TEST_CONFIGURATION__['device_id']})
    except TypeError:
        print("Could not readout device information.")
        __TEST_CONFIGURATION__['device_id']['reading'] = []
    sleep(__READ_TIMEOUT__)

    for key in __TEST_CONFIGURATION__['device_info']:
        print("   Read " + __TEST_CONFIGURATION__['device_info'][key]['comment'] + " ... ", end='')
        data = modbus_connection.read_holding_registers(__TEST_CONFIGURATION__['device_info']
                                                        [key]['address_dec'],
                                                        __TEST_CONFIGURATION__['device_info']
                                                        [key]['count'])
        if key == "get_dev_motor_status":
            # Manual defined pass values for motor control status
            if str(data[0]) not in ["27", "31"]:
                print(data[0], " Fail")
            else:
                print(data[0], " Pass")
        else:
            print(data[0], " Pass")
        __TEST_CONFIGURATION__['device_info'][key]['reading'] = data[0]
        device_info.update({key: __TEST_CONFIGURATION__['device_info'][key]})
        sleep(__PRINT_TIMEOUT__)
    sleep(__READ_TIMEOUT__)
    print("   Done!")
    return device_info


def device_measurement_read_test(modbus_connection: modbus_client) -> list:
    """
    Readout of selected values
    :param modbus_connection: Connection object
    :return: Selected values
    """
    measurement_data_test = {}
    measurement_data = {}
    print("-> Running Measurement Read test: ")
    print("   Measurement parameters -> Count: " + str(__PROBE_COUNT__) + " Offset: " + str(
        __PROBE_OFFSET__) + "s Total time: " + str(__PROBE_COUNT__ * __PROBE_OFFSET__) + "s")
    print("   ", end='')
    for i in range(0, __PROBE_COUNT__):
        print(". ", end='')
        for measurement_type in __TEST_CONFIGURATION__['test_readings_sequence']:
            data = modbus_connection.read_holding_registers(
                __TEST_CONFIGURATION__['test_readings_sequence'][measurement_type]['address_dec'],
                __TEST_CONFIGURATION__['test_readings_sequence'][measurement_type]['count'])
            data_tmp = []
            for data_entry in data:
                data_tmp.append(normalize_integer_value(data_entry))
            __TEST_CONFIGURATION__['test_readings_sequence'][measurement_type]['reading'] = data_tmp
            measurement_data_test.update(
                {measurement_type: __TEST_CONFIGURATION__['test_readings_sequence'][measurement_type]})
            sleep(__READ_TIMEOUT__)
        sleep(__PROBE_OFFSET__)
        measurement_data.update({str(i): measurement_data_test})
    print("Pass")
    print("   Done!")
    return measurement_data


def main() -> None:
    """
    Base structure for testing of ModbusTCPClient module in python.
    :return: String representation of readied / written data
    """
    results = {}
    # Random ID generate
    test_id = uuid.uuid4()
    results.update({"TestID": str(test_id).rsplit('-', maxsplit=1)[-1]})
    now = datetime.now()
    now = now.strftime(__TIME_FORMAT__)
    results.update({"TestTime": now})

    # Definition of variable connection (error suppress)
    connection = None
    # Handling of input parameters with the module parser
    parser = argparse.ArgumentParser(description='Schneider circuit breaker Tester')
    parser.add_argument('--test_mode', dest='mode', type=str, help='Test mode [full, split]',
                        default="full", required=False)
    parser.add_argument('--device_address', dest='address', type=str, help='Device IPv4 address', required=True)
    parser.add_argument('--device_address_split', dest='address_split', type=str, help='Device IPv4 address',
                        required=False)
    parser.add_argument('--device_port', dest='port', type=int, help='Modbus port, default: 502', default=502,
                        required=False)
    parser.add_argument('--device_port_split', dest='port_split', type=int, help='Modbus port, default: 502',
                        default=502,
                        required=False)
    parser.add_argument('--device_uid', dest='uid', type=int, help="Slave UID, default: 255", default=255,
                        required=False)
    parser.add_argument('--device_uid_split', dest='uid_split', type=int, help="Slave UID, default: 255", default=255,
                        required=False)
    parser.add_argument('--config', dest='config', type=str,
                        help="Path to configuration file, default: config/config.yaml",
                        default="config/config.yaml", required=False)
    parser.add_argument('--output', dest='output', type=str, help="file, pdf, dump, db", default="dump", required=False)

    args = parser.parse_args()
    # Loading test settings
    load_test_configuration(args.config)

    if connection_test(args.address, args.port):
        match args.mode:
            # If full then run all the tests
            case "full":
                connection = device_connection(args.address, args.port)
                results.update({"ControlTest": remote_control_test(connection)})
                sleep(__WRITE_TIMEOUT__)
                results.update({"ReadInfoTest": device_information_read_test(connection)})
                sleep(__WRITE_TIMEOUT__)
                results.update({"ReadValuesTest": device_measurement_read_test(connection)})
            # If split then run only remote control on first device, other tests on split device
            case "split":
                connection = device_connection(args.address, args.port)
                results.update({"ControlTest": remote_control_test(connection)})
                sleep(__WRITE_TIMEOUT__)
                if connection_test(args.address_split, args.port_split):
                    results.update({"ReadInfoTest": device_information_read_test(connection)})
                    sleep(__WRITE_TIMEOUT__)
                    results.update({"ReadValuesTest": device_measurement_read_test(connection)})

    match args.output:
        case "json":
            generate_test_report_json(results, __TEST_CONFIGURATION__['config'])
        case "dump":
            print(results)
        case "pdf":
            generate_test_report_html(results, __TEST_CONFIGURATION__['config'])
        case "db":
            write_test_results_2_db(results, __TEST_CONFIGURATION__['config']['db'])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting on Interupt!")
