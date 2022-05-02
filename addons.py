#!/usr/bin/python3.10
"""
Additions module for modbus_protocol.py
"""
import pymysql


def create_db_connection(db_config: dict) -> list:
    """
    Creates MySQL connection usin PyMySQL module
    :param db_config: test config
    :return: [cursor,connection,error]
    """
    error = ""
    sql_cur = None
    sql_conn = None
    try:
        sql_conn = pymysql.connect(host=db_config['address'], user=db_config['user'], password=db_config['password'],
                                   database=db_config['db_name'], charset='utf8')
        sql_cur = sql_conn.cursor()
    except ConnectionError:
        error = "ConnectionError"
    except FileNotFoundError:
        error = "FileNotFoundError"
    return sql_cur, sql_conn, error


def execute_query(query: str, db_config: dict) -> list:
    """
    Wrapper for MySQL query execution
    :param query: SQL quesry as string
    :param db_config: db connection config
    :return: [data, err]
    """
    data = []
    # Creates connection to DB
    curr, conn, err = create_db_connection(db_config)
    try:
        if not err:
            # Executes query
            curr.execute(query)
        data = [item for item in curr.fetchall()]
        conn.commit()
        conn.close()

    except pymysql.err.ProgrammingError:
        err = "Syntax Problem, check query"
    except pymysql.err.InternalError:
        err = "Internal Error"
    return data, err


def generate_test_report_json(results: dict, config: dict) -> None:
    """
    Creates report in JSON format
    :param results: dict of test results
    :param config: dict of test configuration
    :return: None
    """
    try:
        file = open(config['dump_dir'] + str(results['TestID']) + ".json", 'w', encoding='utf-8')
        # replaces single ' for double "
        file.write(str(results).replace("\'", "\""))
        file.close()
    except FileNotFoundError:
        print("Wrong file path!")
        exit(2)
    print("Test data saved: " + config['dump_dir'] + str(results['TestID']) + ".json")


def generate_test_report_html(results: dict, config: dict) -> None:
    """
    Creates report in HTML format
    :param results: dict of test results
    :param config: dict of test configuration
    :return: None
    """
    report, template = None, None
    try:
        # Opens template file and creates new file object for the report
        template = open(config['template_dir'] + config['report_template_file'], 'r', encoding='utf-8').read()
        report = open(config['report_dir'] + str(results['TestID']) + ".html", 'w', encoding='utf-8')
    except FileNotFoundError:
        print("Wrong file path!")
        exit(2)
    # Replaces dummy values in the template for real values from results dictionary
    template = template.replace("test_id", str(results['TestID']))
    template = template.replace("stamp", str(results['TestTime']))
    template = template.replace("t_on_val", str(bool(results['ControlTest']['t_on_c_break']['status'])))
    template = template.replace("t_off_val", str(bool(results['ControlTest']['t_off_c_break']['status'])))
    template = template.replace("t_res_val", str(bool(results['ControlTest']['t_reset_c_break']['status'])))

    template = template.replace("dev_stat_val", str(results['ReadInfoTest']['get_dev_status']['reading']))
    template = template.replace("dev_id_val", str(1))
    template = template.replace("mot_stat_val", str(results['ReadInfoTest']['get_dev_motor_status']['reading']))
    template = template.replace("unit_stat_val", str(results['ReadInfoTest']['get_unit_status']['reading']))

    for test_no in results['ReadValuesTest']:
        for value in results['ReadValuesTest'][test_no]:
            for reading in results['ReadValuesTest'][test_no][value]['value_name']:
                index = list(results['ReadValuesTest'][test_no][value]['value_name']).index(reading)
                replace_string = (str(int(test_no)) + "_" + str(reading).lower())
                value_string = str(results['ReadValuesTest'][test_no][value]['reading'][index])
                if "base_reactive_power" in value:
                    replace_string = replace_string.replace("q", "r")
                template = template.replace(replace_string, value_string)
    report.write(template)
    report.close()
    print("-> Generated report saved! See: " + config['report_dir'] + str(results['TestID']) + ".html")


def write_test_results_2_db(results: dict, db_config: dict) -> None:
    """
    Writes test results into MySQL DB
    :param results: dict of test results
    :param db_config: dict of db config
    :return: None
    """
    try:
        # Query for first table
        base_test_query = "INSERT INTO " + db_config['base_table'] + " VALUES ('" + str(
            results['TestID']) + "','" + str(
            results['TestTime']) + "','" + str(results['ReadInfoTest']['device_id']['reading']).replace("'",
                                                                                                        "\"") + "'," + str(
            results['ReadInfoTest']['get_dev_status']['reading']) + "," + str(
            results['ReadInfoTest']['get_dev_motor_status']['reading']) + "," + str(
            results['ReadInfoTest']['get_unit_status']['reading']) + "," + str(
            results['ControlTest']['t_on_c_break']['status']) + "," + str(
            results['ControlTest']['t_off_c_break']['status']) + "," + str(
            results['ControlTest']['t_reset_c_break']['status']) + ");"
        execute_query(base_test_query, db_config)[0]
        for entry in results['ReadValuesTest']:
            # Query for measurement table
            measurement_query = "INSERT INTO " + db_config['measurement_table'] + " VALUES ('" + str(
                results['TestID']) + "-" + str(entry) + "','" + str(results['TestID']) + "','" + str(
                results['TestTime']) + "'," + str(entry) + ",'" + str(
                results['ReadValuesTest'][entry]['voltage']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['voltage_unbalance']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['current']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['current_unbalance']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['power']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['reactive_power']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['apparent_power']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['efficiency']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['base_efficiency']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['frequency']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['base_reactive_power']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['distortion']['reading']) + "','" + str(
                results['ReadValuesTest'][entry]['global_harm_dist']['reading']) + "');"
            execute_query(measurement_query, db_config)[0]
        print("-> Writing to DB successful!")
    except pymysql.err.IntegrityError:
        print("Writing to DB failed, TestID exists, please run test again!")
