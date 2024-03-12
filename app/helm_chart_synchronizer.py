#!/usr/bin/env python3

import os
import tempfile
import sys
import yaml
import re
import argparse
import pathlib
import time
from datetime import datetime

from subprocess import run, CalledProcessError
from multiprocessing import Pool, ProcessError

REQUIRED_ENVIRONMENT_VARIABLES = {
    "COMMON": [ "ARTIFACT_REGISTRY_PROJECT_ID", "ARTIFACT_REGISTRY_HOSTNAME", "DEBUG" ]
}


########################################################################
#
# Checks that all required environment variables are set
#
def check_environment_variables ():

    missing = []

    for env_var in REQUIRED_ENVIRONMENT_VARIABLES[ "COMMON" ]:

        if os.environ.get(env_var) is None:
            missing.append(env_var)

    if missing != []:

        print("[FATAL]", file=sys.stderr)
        print(f"[FATAL] The following environment variables have not been set and are required:", file=sys.stderr)
        print(f"[FATAL]  {missing}" , file=sys.stderr)
        print("[FATAL]", file=sys.stderr)
        return False

    return True


##########################################################################
#
# Tries to sync an chart from its source registry to its target registry
# It is meant to be run as a Process returning the lists: logs and synced_charts
#
def execute_cli_command (command, error_message, logs, capture_output=True, check=True, shell=True, text=True):

    command_result=None

    try:

        print(f"[DEBUG] COMMAND: {command}", file=sys.stderr)
        command_result = run(command, capture_output=capture_output, check=check, shell=shell, text=text)

    except CalledProcessError as e:

        logs.append(f"[ERROR] {error_message}")
        logs.append(f"[ERROR] {e}")
        logs.append(f"[ERROR] stderr: {e.stderr} - stdout: {e.stdout}")
        return False

    except Exception as exc:

        logs.append(f"[ERROR] {error_message}")
        logs.append(f"[ERROR] {exc}")
        return False

    return True


##########################################################################
#
# Tries to sync an chart from its source registry to its target registry
# It is meant to be run as a Process returning the lists: logs and synced_charts
#
def sync_chart (chart):

    logs = []
    synced_charts = []
    errors = 0

    source_registry = chart["src"].split("/")[0]

    name = "/".join(chart["src"].split("/")[1:])
    source_repository = name.split("/")[0]

    destination = f"oci://{os.environ['ARTIFACT_REGISTRY_HOSTNAME']}/{os.environ['ARTIFACT_REGISTRY_PROJECT_ID']}/{chart['dst']}"

    versions = chart["versions"]
    if versions == []:

        logs.append(f"[ERROR] At least one tag must be specified for {name}")

    else:

        with tempfile.TemporaryDirectory() as tmpdirname:

            for version in versions:

                logs.append("[INFO] ---------------------------------------------------------------------------------------")
                logs.append(f"[INFO] PROCESSING {name} version {version}")

                logs.append(f"[INFO] Adding Helm repository locally: {source_registry}")

                command = f"helm repo add {source_repository} https://{source_registry}"
                error_message = f"Failed to add Helm repo locally: {source_registry}"
                if not execute_cli_command (command, error_message, logs ):
                  print(f"[DEBUG] ERROR + 1", file=sys.stderr)
                  errors += 1
                  continue

                command = f"helm repo update"
                error_message = f"Failed to update local repository cache"
                if not execute_cli_command (command, error_message, logs ):
                  errors += 1
                  continue

                logs.append(f"[INFO] Pulling Helm chart {name} version {version}")
                command = f"helm pull {name} --version {version}"
                error_message = f"Failed to pull chart {name}"
                if not execute_cli_command (command, error_message, logs ):
                  errors += 1
                  continue

                # Generate the pulled chart file name
                chart_short_name=f"{name.split('/')[-1]}"
                pulled_chart = f"{chart_short_name}-{version}.tgz"

                logs.append(f"[INFO] Pushing Helm chart file {pulled_chart} to {destination}")
                command = f"helm push {pulled_chart} {destination}"
                error_message = f"Failed to push chart file {pulled_chart} to {destination}"
                if not execute_cli_command (command, error_message, logs ):
                  errors += 1
                  continue

                logs.append(f"[INFO] SUCCESS - chart {name} version {version} pushed to {destination} ")

                synced_charts.append(f"{pulled_chart}")


    result = {}
    result["logs"] = logs
    result["synced_charts"] = synced_charts
    result["errors"] = errors
    return result


##################################################################################
#
# Main
#
def main (charts_file, num_parallel_tasks):

    check_environment_variables() or sys.exit(1)

    artifact_registry_project_id = os.environ["ARTIFACT_REGISTRY_PROJECT_ID"]
    artifact_registry_hostname = os.environ["ARTIFACT_REGISTRY_HOSTNAME"]
    debug = os.environ["DEBUG"].lower() in ['true',1,'yes','y']

    print("[INFO] ===============================================")
    print(f"[INFO] ARTIFACT_REGISTRY_PROJECT_ID: {artifact_registry_project_id}")
    print(f"[INFO] ARTIFACT_REGISTRY_HOSTNAME: {artifact_registry_hostname}")
    print(f"[INFO] DEBUG: {debug}")

    synced_charts = []
    errors = 0

    command_result=None
    try:
        command_result = run(f"gcloud auth list", capture_output=True, check=True, shell=True, text=True)
    except CalledProcessError as e:
        print("[FATAL] Failed to list credentials")
        print(f"[FATAL] {e}")
        print(f"[FATAL] {e.stderr}")
        sys.exit(1)

    try:
        command_result = run(f"gcloud auth configure-docker {artifact_registry_hostname}", capture_output=True, check=True, shell=True, text=True)
    except CalledProcessError as e:
        print(f"[FATAL] Failed to authenticate against {artifact_registry_hostname}")
        print(f"[FATAL] {e}")
        print(f"[FATAL] {e.stderr}")
        sys.exit(2)

    charts = None
    with open(charts_file) as f:
        charts = yaml.safe_load(f)

    # Avoid issues when the list is shorter than the requested number of parallel processes
    if len(charts) < num_parallel_tasks:
        num_parallel_tasks=len(charts)

    print(f"[INFO] {len(charts)} charts to process in parallel with {num_parallel_tasks} workers.")

    i=0
    chunk_size = int(len(charts)/num_parallel_tasks)

    with Pool(num_parallel_tasks) as p:

        for result in p.imap_unordered(sync_chart, charts, chunk_size):

            i += 1
            synced_charts += result["synced_charts"]
            errors += result["errors"]

            print(f"[INFO] {i} charts processed with {len(synced_charts)} tags updated so far...")

            for log in result["logs"]:
                print(log)

        p.close()
        p.join()


    print("[INFO]")
    print("[INFO] ===================================================================================================")
    print(f"[INFO] {len(synced_charts)} tags synced from {len(charts)} charts defined in input file")
    print(f"[INFO] Errors: {errors}")
    print("[INFO] ===================================================================================================")


if __name__ == '__main__':
    parser = argparse.ArgumentParser( description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('charts_file', metavar="< relative or absolute path to the charts YAML file >", help='The relative or absolute path to the YAML file that contains the list of Helm charts and versions to be synchronized.')
    parser.add_argument('-n','--num-parallel-tasks', type = int, required = False, default = 10, metavar="NUM_PARALLEL_TASKS", help='The max number of parallel tasks')
    args = parser.parse_args()
    main(args.charts_file, args.num_parallel_tasks)
