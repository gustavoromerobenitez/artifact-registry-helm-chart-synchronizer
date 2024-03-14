#!/usr/bin/env python3

import os
import tempfile
import sys
import yaml
import argparse
import pathlib

# Static Code Analysis of pulled Helm charts
import checkov


from subprocess import run, CalledProcessError
from multiprocessing import Pool, ProcessError

REQUIRED_ENVIRONMENT_VARIABLES = {
  "COMMON": [ "ARTIFACT_REGISTRY_PROJECT_ID", "ARTIFACT_REGISTRY_HOSTNAME", "DEBUG" ]
}


########################################################################
#
# Checks that all environment variables passed as argument are set
#
def check_environment_variables ( environment_vars ):

  missing = []

  for env_var in environment_vars:

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
# Executes a CLI command
#
# In case of failure it will return the error logs and raise an Exception
#   to allow upstream code to react to the failure, if required
#
def execute_cli_command (command, error_message, logs, capture_output=True, check=True, shell=True, text=True):

  command_result=None

  try:

    print(f"[DEBUG] COMMAND: {command}", file=sys.stderr)
    command_result = run(command, capture_output=capture_output, check=check, shell=shell, text=text)

  except CalledProcessError as e:

    logs.append(f"[ERROR] {error_message}")
    logs.append(f"[ERROR] {e}")
    logs.append(f"[ERROR] {e.stderr}")
    raise Exception("Command execution failed")

  except Exception as exc:

    logs.append(f"[ERROR] {error_message}")
    logs.append(f"[ERROR] {exc}")
    raise Exception("Command execution failed")

  return True


############################################################################################
#
# Pulls a chart from its source registry
#  and pushes it to its target repository in Artifact Registry
#
# This function is meant to be run as a Process returning the lists: logs and synced_charts
#
def sync_chart (chart):

  logs = []
  synced_charts = []
  errors = 0
  result = {}

  source_registry = chart["source"].split("/")[0]

  name = "/".join(chart["source"].split("/")[1:])
  source_repository = name.split("/")[0]

  destination_repo = chart["destination"].split("/")[0]
  destination_registry = f"oci://{os.environ['ARTIFACT_REGISTRY_HOSTNAME']}/{os.environ['ARTIFACT_REGISTRY_PROJECT_ID']}"
  destination_full_path = f"{destination_registry}/{chart['destination']}"  # chart['destination'] contains the repository and the chart name

  versions = chart["versions"]

  if versions == []:

      logs.append(f"[ERROR] At least one tag must be specified for {name}")

  else:

    try:

      logs.append(f"[INFO] Adding Helm repository locally: {source_registry}")

      command = f"helm repo add {source_repository} https://{source_registry}"
      error_message = f"Failed to add Helm repo locally: {source_registry}"
      execute_cli_command (command, error_message, logs )

      command = f"helm repo update"
      error_message = f"Failed to update local repository cache"
      execute_cli_command (command, error_message, logs )

    except Exception as e:
      logs.append(f"[ERROR] Exception: {e} ")
      errors += len(versions)


    with tempfile.TemporaryDirectory() as tmpdir:

      os.chdir(os.path.abspath(tmpdir))

      for version in versions:

        error = False

        logs.append("[INFO] ---------------------------------------------------------------------------------------")
        logs.append(f"[INFO] PROCESSING {name} version {version}")

        try:

          logs.append(f"[INFO] Adding Helm repository locally: {source_registry}")

          command = f"helm repo add {source_repository} https://{source_registry}"
          error_message = f"Failed to add Helm repo locally: {source_registry}"
          execute_cli_command (command, error_message, logs )

          command = f"helm repo update"
          error_message = f"Failed to update local repository cache"
          execute_cli_command (command, error_message, logs )

          logs.append(f"[INFO] Pulling Helm chart {name} version {version}")

          command = f"helm pull {name} --version {version}"
          error_message = f"Failed to pull chart {name}"
          execute_cli_command (command, error_message, logs )

          # Generate the pulled chart file name
          chart_short_name=f"{name.split('/')[-1]}"
          pulled_chart = f"{chart_short_name}-{version}.tgz"

          logs.append(f"[INFO] Pushing Helm chart file {pulled_chart} to {destination_full_path}")

          command = f"helm push {pulled_chart} {destination_full_path}"
          error_message = f"Failed to push chart file {pulled_chart} to {destination_full_path}"
          execute_cli_command (command, error_message, logs )

          logs.append(f"[INFO] SUCCESS - chart {name} version {version} pushed to {destination_full_path} ")
          synced_charts.append(f"{pulled_chart}")

        except Exception as e:
          logs.append(f"[ERROR] Exception: {e} ")
          errors +=1


  result["logs"] = logs
  result["synced_charts"] = synced_charts
  result["errors"] = errors

  return result


##########################################################
#
# Performs authentication against all registries involved
#  i.e.: Artifact Regsitry and any authenticated regsitries
#         declared in the config file
#
def authenticate_against_registries (charts):

  authentication_logs = []

  print(f"[INFO] Authenticating against Artifact Registry at {artifact_registry_hostname} ...")

  try:

    command = f"gcloud auth configure-docker {artifact_registry_hostname}"
    error_message = f"[FATAL] Failed to authenticate against {artifact_registry_hostname}"
    execute_cli_command (command, error_message, authentication_logs )

  except Exception as e:

    for log in authentication_logs:
        print(log)

    sys.exit(1)

  # Check authentication against the authenticatedRegistries declared in the file, if there are any
  if "authenticatedRegistries" in config.keys():

    for registry in charts["authenticatedRegistries"]:

      # The username and password should be present in environment variables
      #  named like the registry they belong to,
      #  i.e.: REGISTRY_1_MYORG_COM_USERNAME, REGISTRY_1_MY_ORG_COM_PASSWORD
      username_env_var_name = f'{registry.upper().replace("-","_").replace(".","_")}_USERNAME'
      password_env_var_name = f'{registry.upper().replace("-","_").replace(".","_")}_PASSWORD'

      check_environment_variables( [ username_env_var_name, password_env_var_name ] ) or sys.exit(3)

      username = os.environ[ username_env_var_name ]
      password = os.environ[ password_env_var_name ]

      print(f"[INFO] Authenticating against the Helm registry at {registry} ...")

      try:

        command = f"helm registry login {registry} --username {username} --password {password}"
        error_message = f"Failed to log on to {registry} using the provided credentials"
        # execute_cli_command (command, error_message, authentication_logs )

      except CalledProcessError as e:

        for log in authentication_logs:
          print(log)

        print(f"[FATAL] Failed to authenticate against {registry}")

        sys.exit(2)


##################################################################################
#
# Main
#
def main (charts_file, num_parallel_tasks):

  check_environment_variables( REQUIRED_ENVIRONMENT_VARIABLES[ "COMMON" ] ) or sys.exit(1)

  artifact_registry_project_id = os.environ["ARTIFACT_REGISTRY_PROJECT_ID"]
  artifact_registry_hostname = os.environ["ARTIFACT_REGISTRY_HOSTNAME"]
  debug = os.environ["DEBUG"].lower() in ['true',1,'yes','y']

  print("[INFO] ==================================================================================")
  print(f"[INFO] ARTIFACT_REGISTRY_PROJECT_ID: {artifact_registry_project_id}")
  print(f"[INFO] ARTIFACT_REGISTRY_HOSTNAME: {artifact_registry_hostname}")
  print(f"[INFO] DEBUG: {debug}")
  print("[INFO] ==================================================================================")

  config = None
  with open(charts_file) as f:
      config = yaml.safe_load(f)

  authenticate_against_registries (config)

  # Limit the number of parallel processes to avoid issues
  # when the chart list is shorter than the requested number of parallel processes
  charts = config['charts']
  if len(charts) < num_parallel_tasks:
      num_parallel_tasks=len(charts)

  print(f"[INFO] {len(charts)} charts to process in parallel with {num_parallel_tasks} workers.")

  i=0
  synced_charts = []
  errors = 0
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
