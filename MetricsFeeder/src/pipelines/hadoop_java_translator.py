#!/usr/bin/env python
from __future__ import print_function
import sys
import fileinput
import pickle
from time import sleep
import os

JAVA_MAPPINGS_FOLDER_PATH = "JAVA_MAPPINGS_FOLDER_PATH"
JAVA_TRANSLATOR_MAX_TRIES = "JAVA_TRANSLATOR_MAX_TRIES"
JAVA_TRANSLATOR_WAIT_TIME = "JAVA_TRANSLATOR_WAIT_TIME"

java_mappings_folder_path = os.getenv(JAVA_MAPPINGS_FOLDER_PATH, "./pipelines/java_mappings/")
java_translator_max_tries = int(os.getenv(JAVA_TRANSLATOR_MAX_TRIES, 4))
java_translator_wait_time = int(os.getenv(JAVA_TRANSLATOR_WAIT_TIME, 5))

process_files = ["NameNode", "SecondaryNameNode", "DataNode", "ResourceManager", "NodeManager",
                 "YarnChild", "MRAppMaster", "CoarseGrainedExecutorBackend", "OTHER"]

java_proc_dict = dict()
unresolvable_pids = list()


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def read_process_pids_from_file(process_name):
    try:
        with open(java_mappings_folder_path + process_name + '.txt', 'r') as content_file:
            itemlist = pickle.load(content_file)
        itemlist = [int(x) for x in itemlist]
        # print "Loaded list is: " + str(itemlist)
        return itemlist
    except IOError:
        return []


def read_all():
    global java_proc_dict
    for proc_file in process_files:
        pid_list = read_process_pids_from_file(proc_file)
        java_proc_dict[proc_file] = pid_list


def process_java_doc(line, pid, number_of_tries):
    global java_proc_dict
    global unresolvable_pids

    if pid in unresolvable_pids:
        return line.strip()

    for process_name in process_files:
        process_pids = java_proc_dict[process_name]
        # print "Process pids for " + process_name + " are: " + str(process_pids) + " and pid is : " + str(pid)
        if pid in process_pids:
            return line.replace("(java)", process_name).strip()
    # return line changed
    # Couldn't resolve this doc, wait, read map files and try again
    # Wait for a max of 60 seconds
    if number_of_tries < java_translator_max_tries:
        sleep(java_translator_wait_time)
        read_all()
        number_of_tries += 1
        return process_java_doc(line, pid, number_of_tries)
    else:
        eprint("[HADOOP JAVA TRANSLATOR PLUGIN] process java with pid " + str(pid) + " was unresolvable")
        unresolvable_pids.append(pid)
        return line.strip()


read_all()


def process_line(line):
    if line.startswith('P'):
        fields = line.split(",")
        command = fields[5]
        pid_str = fields[4]
        if line.startswith('PRM'):
            command = fields[4]  # Override for this case
            pid_str = fields[3]
        if command == "(java)":
            return process_java_doc(line, int(pid_str), 0)
        else:
            return line.strip()
    elif line.startswith("NETHOGS"):
        fields = line.split(",")
        command = fields[5]
        pid_str = fields[6]
        if command == "(java)":
            return process_java_doc(line, int(pid_str), 0)
        else:
            return line.strip()
    else:
        return line.strip()


def behave_like_pipeline():
    try:
        #for line in fileinput.input():
        while True:
            line = sys.stdin.readline()
            print(process_line(line))
    except (KeyboardInterrupt, IOError):
        # Exit silently
        pass
    except Exception as e:
        eprint("[JSON TO VALID_JSON] error: " + str(e))


def main():
    behave_like_pipeline()


if __name__ == "__main__":
    main()