#!/usr/bin/env python
from __future__ import print_function
import sys
import os
import subprocess
import signal
from daemon import runner
import socket

import MetricsFeeder.src.daemons.daemon_utils as daemon_utils
from MetricsFeeder.src.daemons.daemon_utils import MonitoringDaemon

_base_path = os.path.dirname(os.path.abspath(__file__))
SERVICE_NAME = "Atop_" + str(socket.gethostname())

config_path = "conf/atop_config.ini"
config_keys = [
    "ATOP_SAMPLING_FREQUENCY",
    "METRICS",
    "POST_ENDPOINT_PATH",
    "POST_DOC_BUFFER_TIMEOUT",
    "PYTHONUNBUFFERED",
    "TEMPLATE_PATH",
    "METRICS_PATH",
    "TAGS_PATH",
    "POST_DOC_BUFFER_LENGTH",
    "POST_SEND_DOCS_TIMEOUT",
    "POST_SEND_DOCS_FAILED_TRIES",
    "JAVA_MAPPINGS_FOLDER_PATH",
    "JAVA_TRANSLATOR_MAX_TRIES",
    "JAVA_TRANSLATOR_WAIT_TIME",
    "HADOOP_SNITCH_FOLDER_PATH",
    "JAVA_TRANSLATION_ENABLED",
    "HEARTBEAT_ENABLED"
]
default_environment_values = {
    "ATOP_SAMPLING_FREQUENCY": "10",
    "METRICS": "CPU,cpu,MEM,SWP,DSK,NET,PRC,PRM,PRD,PRN",
    "POST_ENDPOINT_PATH": "http://opentsdb:4242/api/put",
    "POST_DOC_BUFFER_TIMEOUT": "30",
    "PYTHONUNBUFFERED": "yes",
    "TEMPLATE_PATH": os.path.join(_base_path, "../pipelines/templates/"),
    "METRICS_PATH": os.path.join(_base_path, "../pipelines/metrics/"),
    "TAGS_PATH": os.path.join(_base_path, "../pipelines/tags/"),
    "POST_DOC_BUFFER_LENGTH": "1000",  # Don't go over 1500 or post packet will be too large and may cause error
    "POST_SEND_DOCS_TIMEOUT": "30",
    "POST_SEND_DOCS_FAILED_TRIES": "6",
    "JAVA_MAPPINGS_FOLDER_PATH": os.path.join(_base_path, "../pipelines/java_mappings/"),
    "JAVA_TRANSLATOR_MAX_TRIES": "4",
    "JAVA_TRANSLATOR_WAIT_TIME": "3",
    "HADOOP_SNITCH_FOLDER_PATH": os.path.join(_base_path, "../java_hadoop_snitch/"),
    "JAVA_TRANSLATION_ENABLED": "false",
    "HEARTBEAT_ENABLED": "false"
}

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def atop_is_runnable(environment):
    # Run a bogus 'atop' command, show CPU usage every 1 seconds, 1 time
    # If the command doesn't fail, atop works
    return daemon_utils.command_is_runnable(['atop', '1', '1', '-P', 'CPU'])


class Atop(MonitoringDaemon):

    def run(self):
        # Launch Java snitch if java translation is going to be used
        # if self.environment["JAVA_TRANSLATION_ENABLED"] == "true":
        #     self.snitcher = self.launch_java_snitch()

        self.launch_pipeline()
        self.launch_heartbeat()
        self.loop()

    def create_pipeline(self):
        processes_list = []

        # Create the data source
        atop = subprocess.Popen(
            ['atop', self.environment["ATOP_SAMPLING_FREQUENCY"], '-P', self.environment["METRICS"]],
            stdout=subprocess.PIPE)

        processes_list.append(atop)

        # Create the data pipeline
        if self.environment["JAVA_TRANSLATION_ENABLED"] == "true":
            # With JAVA mapping
            atop_to_json = self.create_pipe(
                [os.path.join(_base_path, "../atop/atop_to_json_with_java_translation.py")], self.environment,
                atop.stdout,
                subprocess.PIPE)
        else:
            # Without JAVA mapping
            # TODO FIX, python version should not be hard-coded
            atop_to_json = self.create_pipe(
                ["python3", os.path.join(_base_path, "../atop/atop_to_json.py")], self.environment,
                atop.stdout,
                subprocess.PIPE)
        # TODO FIX, python version should not be hard-coded
        send_to_opentsdb = self.create_pipe(["python2", os.path.join(_base_path, "../pipelines/send_to_OpenTSDB.py")],
                                            self.environment,
                                            atop_to_json.stdout, subprocess.PIPE)
        processes_list.append(send_to_opentsdb)

        return processes_list

    def launch_java_snitch(self):
        # Create the java snitch process
        java_snitch_process = subprocess.Popen(
            ["python", os.path.join(_base_path, "../java_hadoop_snitch/java_snitch.py")],
            env=self.environment, stdout=subprocess.PIPE)
        return java_snitch_process


if __name__ == '__main__':
    handler, logger = daemon_utils.configure_daemon_logs(SERVICE_NAME)

    app = Atop(SERVICE_NAME, logger)
    # FIXME As part of the environment initilization, set the pythonpath correctly
    app.initialize_environment(config_path, config_keys, default_environment_values)
    app.is_runnable = atop_is_runnable
    app.not_runnable_message = "Atop program is not runnable or it is installed, " \
                               "if installed run atop manually and check for errors"
    app.check_if_runnable()

    # Capture reload signal and propagate
    signal.signal(signal.SIGHUP, app.reload_pipeline)

    # Run service
    serv = runner.DaemonRunner(app)
    serv.daemon_context.files_preserve = [handler.stream]
    serv.do_action()