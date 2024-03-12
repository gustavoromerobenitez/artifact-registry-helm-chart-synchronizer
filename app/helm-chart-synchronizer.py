#!/usr/bin/env python3

import sys
import yaml
import re
import argparse
import pathlib
import time
from datetime import datetime

from subprocess import run, CalledProcessError
from multiprocessing import Pool, ProcessError # Process, Manager

PROJECT_ID="" # ARG
ARTIFACT_REGISTRY = "oci://europe-docker.pkg.dev"


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
    
    destination = f"{ARTIFACT_REGISTRY}/{chart['dst']}"

    versions = chart["versions"]
    if versions == []:
        logs.append(f"[ERROR] At least one tag must be specified for {name}")

    for version in versions:

        logs.append("[INFO] ---------------------------------------------------------------------------------------")
        logs.append(f"[INFO] PROCESSING {name} version {version}")

        logs.append(f"[INFO] Adding Helm repository locally: {source_registry}")
        command_result=None
        try:
            command_result = run(f"helm repo add {source_repository} https://{source_registry}", capture_output=True, check=True, shell=True, text=True)
        except CalledProcessError as e:
            errors += 1
            logs.append(f"[ERROR] Failed to add Helm repo locally: {source_registry}")
            logs.append(f"[ERROR] {e}")
            logs.append(f"[ERROR] stderr: {e.stderr} - stdout: {e.stdout}")
            continue

        command_result=None
        try:
            command_result = run(f"helm repo update ", capture_output=True, check=True, shell=True, text=True)
        except CalledProcessError as e:
            errors += 1
            logs.append(f"[ERROR] Failed to update local repository cache")
            logs.append(f"[ERROR] {e}")
            logs.append(f"[ERROR] stderr: {e.stderr} - stdout: {e.stdout}")
            continue

        logs.append(f"[INFO] Pulling Helm chart {name} version {version}")
        command_result=None
        try:
            command_result = run(f"helm pull {name} --version {version}", capture_output=True, check=True, shell=True, text=True)
        except CalledProcessError as e:
            errors += 1
            logs.append(f"[ERROR] Failed to pull chart {name}")
            logs.append(f"[ERROR] {e}")
            logs.append(f"[ERROR] stderr: {e.stderr} - stdout: {e.stdout}")
            continue

        # Generate the pulled chart file name
        chart_short_name=f"{name.split('/')[-1]}"
        pulled_chart = f"{chart_short_name}-{version}.tgz"

        logs.append(f"[INFO] Pushing Helm chart file {pulled_chart} to {destination}")
        command_result=None
        try:
            command_result = run(f"helm push {pulled_chart} {destination}", capture_output=True, check=True, shell=True, text=True)
        except CalledProcessError as e:
            errors += 1
            logs.append(f"[ERROR] Failed to push chart file {pulled_chart} to {destination}")
            logs.append(f"[ERROR] {e}")
            logs.append(f"[ERROR] stderr: {e.stderr} - stdout: {e.stdout}")
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
        command_result = run(f"gcloud auth configure-docker europe-docker.pkg.dev", capture_output=True, check=True, shell=True, text=True)
    except CalledProcessError as e:
        print(f"[FATAL] Failed to authenticate against europe-docker.pkg.dev")
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
    parser.add_argument('charts_file', metavar="< relative or absolute path to the charts YAML file >", help='The relative or absolute path to the YAML file that contains the list of container charts and tags to be synchronized into Copa\'s container registry')
    parser.add_argument('-n','--num-parallel-tasks', type = int, required = False, default = 10, metavar="NUM_PARALLEL_TASKS", help='The max number of parallel tasks')
    args = parser.parse_args()
    main(args.charts_file, args.num_parallel_tasks)
