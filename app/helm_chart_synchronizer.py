#!/usr/bin/env python3

import os
import os.path
import tempfile
import sys
import yaml
import argparse
import inspect
import time
import re

from functools import partial

from subprocess import run, CalledProcessError
from multiprocessing import Pool, ProcessError

CURRENTDIR = os.path.dirname( os.path.abspath( inspect.getfile( inspect.currentframe() ) ) )
CERTIFICATE_BUNDLE_LOCATION = f"{CURRENTDIR}/trusted-certs/ca-bundle.pem"

REQUIRED_ENVIRONMENT_VARIABLES = {
  "COMMON": [ "ARTIFACT_REGISTRY_PROJECT_ID", "ARTIFACT_REGISTRY_HOSTNAME", "VERIFY_CERTIFICATES", "DEBUG" ]
}


########################################################################
#
# Checks that all environment variables passed as argument are set
#
def check_environment_variables ( environment_vars, debug = False, required = False ):

  missing = []

  for env_var in environment_vars:

    if os.environ.get(env_var) is None:
        missing.append(env_var)

  if missing != []:

    log_level="WARNING"
    if required:
      log_level= "FATAL"

    print(f"[{log_level}]", file=sys.stderr)
    print(f"[{log_level}] The following environment variables have not been set:", file=sys.stderr)
    print(f"[{log_level}]  {missing}" , file=sys.stderr)
    print(f"[{log_level}]", file=sys.stderr)
    return False

  return True


##########################################################################
#
# Executes a CLI command
#
# In case of failure it will return the error logs and raise an Exception
#   to allow upstream code to react to the failure, if required
#
def execute_cli_command (command, error_message, logs, debug=False, capture_output=True, check=True, shell=True, text=True):

  command_result=None

  try:

    not debug or logs.append(f"[DEBUG] COMMAND: {command}")
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
# Executes a checkov scan on the helm chart
#
def check_sast (debug):

  bucket_url = None
  run_trivy = run_checkov = False

  if os.environ.get("BUCKET_URL") is not None:

    bucket_url = os.environ[ "BUCKET_URL" ]

    if os.environ.get("RUN_CHECKOV") is not None \
        and os.environ[ "RUN_CHECKOV" ].lower() in ['true',1,'yes','y']:

      run_checkov = True

      if debug:
        os.environ["LOG_LEVEL"] = "DEBUG"

      if os.environ.get("PYTHONUNBUFFERED") is None:
        os.environ["PYTHONUNBUFFERED"] = "1"

      os.environ["ANSI_COLORS_DISABLED"] = "true"

    if os.environ.get("RUN_TRIVY") is not None \
        and os.environ[ "RUN_TRIVY" ].lower() in ['true',1,'yes','y']:

        run_trivy = True

  return (bucket_url, run_trivy, run_checkov)


############################################################################################
#
# Executes trivy and/or checkov scans on the helm chart
#
def run_sast ( trivy, checkov, chart_file_name, chart_name, chart_version, logs, debug = False):

  bucket_url = os.environ[ "BUCKET_URL" ]

  if checkov:

    output_file = f"{chart_name}.{chart_version}.checkov.json"

    try:

      logs.append(f"[INFO] Running checkov scan on the helm chart {output_file}.")
      command = f"tar xf {chart_file_name} && checkov -d {chart_name} -o json --soft-fail --quiet --compact --skip-check CKV_K8S_21,LOW --framework helm,kubernetes,secrets > {output_file}"
      error_message = f"Failed to run checkov on chart {chart_name} version {chart_version}."
      execute_cli_command (command, error_message, logs, debug = debug )

    except Exception as e:
      logs.append(f"[ERROR] Exception: {e} ")

    finally:

      if os.path.isfile(output_file):
        logs.append(f"[INFO] Uploading checkov scan report.")
        command = f"gcloud storage cp {output_file} {bucket_url}"
        error_message = f"Failed to upload checkov scan report {output_file} to bucket {bucket_url}."
        execute_cli_command (command, error_message, logs, debug = debug )


  if trivy:

    output_file = f"{chart_name}.{chart_version}.trivy.json"

    try:

      logs.append(f"[INFO] Running trivy config scan on the helm chart {output_file}.")
      command = f"tar xf {chart_file_name} && trivy config --report summary --misconfig-scanners helm --severity UNKNOWN,HIGH,CRITICAL --format json --quiet {chart_name}"
      if debug:
        command = f"{command} --debug"
      command = f"{command} > {output_file}"
      error_message = f"Failed to run trivy on chart {chart_name} version {chart_version}."
      execute_cli_command (command, error_message, logs, debug = debug )

    except Exception as e:
      logs.append(f"[ERROR] Exception: {e} ")

    finally:

      if os.path.isfile(output_file):
        logs.append(f"[INFO] Uploading trivy scan report.")
        command = f"gcloud storage cp {output_file} {bucket_url}"
        error_message = f"Failed to upload trivy scan report {output_file} to bucket {bucket_url}."
        execute_cli_command (command, error_message, logs, debug = debug )


############################################################################################
#
# Pulls a chart from its source registry
#  and pushes it to its target repository in Artifact Registry
#
# This function is meant to be run as a Process returning the lists: logs and synced_charts
#
def sync_chart ( chart, authenticated_registries, pause_between_operations, destination_registry, verify_certificates, run_trivy, run_checkov, debug):

  logs = []
  synced_charts = []
  errors = 0
  result = {}

  source_registry = chart["registry"]
  source_repository = chart["repository"]
  source_chart_name = chart["chart"]

  logs.append("[INFO] -------------------------------------------------------")
  logs.append(f"[INFO] PROCESSING {source_repository}/{source_chart_name}")

  #
  # If the destination regsitry requires authentication, retrieve its credentials
  #  which should be present as environment variables
  #
  username = password = None
  if authenticated_registries is not None \
        and authenticated_registries != [] \
        and destination_registry in authenticated_registries:

    (username, password) = get_credentials_for_registry(destination_registry, debug)


  destination_repo = chart["destination_repository"]

  # add the source repository to the path to keep the charts organised in tArtifact Registry
  destination_full_path = f"{destination_registry}/{destination_repo}/{source_repository}"

  versions = chart["versions"]

  if versions == []:

      logs.append(f"[ERROR] At least one tag must be specified for {source_repository}/{source_chart_name} at {source_registry}")
      errors += 1

  else:

    command_optional_args = ""
    if verify_certificates:
      command_optional_args = f"{command_optional_args} --ca-file {CERTIFICATE_BUNDLE_LOCATION}"

    if username is not None and password is not None:
      command_optional_args = f"{command_optional_args} --username '{username}' --password '{password}'"

    source_path = f"{source_repository}/{source_chart_name}"

    if source_registry.startswith("oci://"):

      # `helm repo`` commands are not supported for OCI repositories
      # The full path including the registry domain name is required to pull the chart
      source_path = f"{source_registry}/{source_path}"

    else:
      
      try:

        logs.append(f"[INFO] Adding non-OCI Helm repository locally: {source_registry}")

        command = f"helm repo add --force-update {command_optional_args} {source_repository} {source_registry}"
        error_message = f"Failed to add Helm repo locally: {source_registry}"
        execute_cli_command (command, error_message, logs, debug = debug )

        command = f"helm repo update"
        error_message = f"Failed to update local repository cache"
        execute_cli_command (command, error_message, logs, debug = debug )

      except Exception as e:
        logs.append(f"[ERROR] Exception: {e} ")
        errors += len(versions)

      finally:
        time.sleep(pause_between_operations)


    if errors == 0:

       for version in versions:

        with tempfile.TemporaryDirectory() as tmpdir:

          os.chdir(os.path.abspath(tmpdir))

          logs.append(f"[INFO] PROCESSING {source_repository}/{source_chart_name} version {version}")

          destination_chart_name = source_chart_name

          try:

            logs.append(f"[INFO] Pulling Helm chart {source_path} version {version}")

            command = f"helm pull {source_path} --version {version} {command_optional_args}"
            error_message = f"Failed to pull chart {source_path} from {source_registry}"
            execute_cli_command (command, error_message, logs, debug = debug )

            pulled_chart_file_name = f"{source_chart_name}-{version}.tgz"

            if run_trivy or run_checkov:
              run_sast ( run_trivy, run_checkov, pulled_chart_file_name, source_chart_name, version, logs, debug = debug)

            #
            # If the Helm Chart name contains upper case letters, it will be rejected by Artifact Registry
            #   We need to edit the chart name in the Chart.yaml included in the tgz file.
            #
            if re.search(r'^.+[A-Z]', pulled_chart_file_name) is not None:

              new_pulled_chart_file_name = re.sub(r'([A-Z])', lambda m: f"-{m.group(0).lower()}", pulled_chart_file_name)
              new_chart_name = re.sub(r'([A-Z])', lambda m: f"-{m.group(0).lower()}", source_chart_name)

              command = f"tar xf {pulled_chart_file_name} && cd {source_chart_name} && sed -i 's|{source_chart_name}|{new_chart_name}|g' Chart.yaml && helm package . && mv {new_pulled_chart_file_name} ../ && cd .. && rm -rf {source_chart_name}/"
              error_message = f"Failed to replace the chart name {source_chart_name} with {new_chart_name} in Chart.yaml inside the chart file {pulled_chart_file_name}"
              execute_cli_command (command, error_message, logs, debug = debug )

              pulled_chart_file_name = new_pulled_chart_file_name
              destination_chart_name = new_chart_name


            logs.append(f"[INFO] Pushing Helm chart file {pulled_chart_file_name} to {destination_full_path}")

            command = f"helm push {pulled_chart_file_name} {destination_full_path}"
            error_message = f"Failed to push chart file {pulled_chart_file_name} to {destination_full_path}"
            execute_cli_command (command, error_message, logs, debug = debug )

            logs.append(f"[INFO] SUCCESS - chart {destination_chart_name} version {version} pushed to {destination_full_path} ")
            synced_charts.append(f"{pulled_chart_file_name}")

          except Exception as e:
            logs.append(f"[ERROR] Exception: {e} ")
            errors +=1

          finally:
            time.sleep(pause_between_operations)


  result["logs"] = logs
  result["synced_charts"] = synced_charts
  result["errors"] = errors

  return result




########################################################################
#
# Given a Helm chart registry, it retrieves it credentials
#   from environment variables, if they are defined
#
def get_credentials_for_registry(registry, debug = False):

  # The username and password should be present in environment variables
  #  named like the registry they belong to,
  #  i.e.: REGISTRY_1_MYORG_COM_USERNAME, REGISTRY_1_MY_ORG_COM_PASSWORD
  username_env_var_name = f'{registry.upper().replace("-","_").replace(".","_")}_USERNAME'
  password_env_var_name = f'{registry.upper().replace("-","_").replace(".","_")}_PASSWORD'

  check_environment_variables( [ username_env_var_name, password_env_var_name ], debug = debug, required = True) or sys.exit(3)

  username = os.environ[ username_env_var_name ]
  password = os.environ[ password_env_var_name ]

  return (username, password)


##########################################################
#
# Performs authentication against all registries involved
#  i.e.: Artifact Regsitry and any authenticated regsitries
#         declared in the config file
#
def authenticate_against_registries (config, artifact_registry_hostname, verify_certificates = False, debug=False ):

  authentication_logs = []

  print(f"[INFO] Authenticating against Artifact Registry at {artifact_registry_hostname} ...")

  try:

    command = f"gcloud auth configure-docker {artifact_registry_hostname}"
    error_message = f"[FATAL] Failed to authenticate against {artifact_registry_hostname}"
    execute_cli_command (command, error_message, authentication_logs, debug = debug )

  except Exception as e:

    for log in authentication_logs:
        print(log, file=sys.stderr)

    sys.exit(1)

  # Check authentication against the authenticatedRegistries declared in the file, if there are any
  if "authenticatedRegistries" in config.keys():

    for registry in config["authenticatedRegistries"]:

      (username, password) = get_credentials_for_registry(registry, debug)

      print(f"[INFO] Authenticating against the Helm registry at {registry} ...")

      try:

        command = f"helm registry login {registry} --username '{username}' --password '{password}'"

        if verify_certificates:
          command = f"{command} --ca-file {CERTIFICATE_BUNDLE_LOCATION}"

        error_message = f"Failed to log on to {registry} using the provided credentials"
        execute_cli_command (command, error_message, authentication_logs, debug = debug )

      except Exception as e:

        for log in authentication_logs:
          print(log, file=sys.stderr)

        print(f"[FATAL] Failed to authenticate against {registry}", file=sys.stderr)

        sys.exit(2)


##################################################################################
#
# Main
#
def main (charts_file, num_parallel_tasks, pause_between_operations):

  check_environment_variables( REQUIRED_ENVIRONMENT_VARIABLES[ "COMMON" ], required = True ) or sys.exit(1)

  artifact_registry_project_id = os.environ["ARTIFACT_REGISTRY_PROJECT_ID"]
  artifact_registry_hostname = os.environ["ARTIFACT_REGISTRY_HOSTNAME"]
  debug = os.environ["DEBUG"].lower() in ['true',1,'yes','y']
  verify_certificates = os.environ["VERIFY_CERTIFICATES"].lower() in ['true',1,'yes','y']



  print("[INFO] ==================================================================================")
  print(f"[INFO] ARTIFACT_REGISTRY_PROJECT_ID: {artifact_registry_project_id}")
  print(f"[INFO] ARTIFACT_REGISTRY_HOSTNAME: {artifact_registry_hostname}")
  print(f"[INFO] VERIFY_CERTIFICATES: {verify_certificates}")
  print(f"[INFO] PAUSE BETWEEN OPERATIONS: {pause_between_operations}")
  print(f"[INFO] NUMBER OF PARALLEL TASKS: {num_parallel_tasks}")
  print(f"[INFO] DEBUG: {debug}")

  (bucket_url, run_trivy, run_checkov) = check_sast(debug)

  if bucket_url is not None and run_trivy or run_checkov:

    print(f"[INFO] SAST Analysis is enabled:")
    print(f"[INFO]  BUCKET_URL: {bucket_url}")
    print(f"[INFO]  RUN_TRIVY: {run_trivy}")
    print(f"[INFO]  RUN_CHECKOV: {run_checkov}")
    
  print("[INFO] ==================================================================================")

  #
  # Build the absolute path to the charts file if required
  #
  if not charts_file.startswith("/"):
    charts_file = f"{CURRENTDIR}/{charts_file}"

  config = None
  with open(charts_file) as f:
    config = yaml.safe_load(f)

  authenticate_against_registries (config, artifact_registry_hostname, verify_certificates = verify_certificates, debug = debug)

  destination_registry = f"oci://{os.environ['ARTIFACT_REGISTRY_HOSTNAME']}/{os.environ['ARTIFACT_REGISTRY_PROJECT_ID']}"

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

  authenticated_registries = None
  if "authenticatedRegistries" in config.keys():
    authenticated_registries = config['authenticatedRegistries']

  parallel_function = partial ( sync_chart, authenticated_registries = authenticated_registries,
                                            pause_between_operations = pause_between_operations,
                                            destination_registry = destination_registry,
                                            verify_certificates = verify_certificates,
                                            run_trivy = run_trivy, run_checkov = run_checkov, debug = debug )

  with Pool(num_parallel_tasks) as p:

    for result in p.imap_unordered(parallel_function, charts, chunk_size):

      i += 1
      synced_charts += result["synced_charts"]
      errors += result["errors"]

      for log in result["logs"]:
          print(log)

      print("[INFO]")
      print(f"[INFO] Progress: {i} charts processed with {len(synced_charts)} versions updated so far...")
      print("[INFO]")

    p.close()
    p.join()


  print("[INFO]")
  print("[INFO] ===================================================================================================")
  print(f"[INFO] {len(synced_charts)} tags synced from {len(charts)} charts defined in input file")
  print(f"[INFO] Errors: {errors}")
  print("[INFO] ===================================================================================================")


if __name__ == '__main__':
    parser = argparse.ArgumentParser( description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-f','--charts-file', type = str,  required = False, default = "config/charts.yaml", metavar="< relative or absolute path to the charts YAML file >", help='The relative or absolute path to the YAML file that contains the list of Helm charts and versions to be synchronized.')
    parser.add_argument('-n','--num-parallel-tasks', type = int, required = False, default = 10, metavar="NUM_PARALLEL_TASKS", help='The max number of parallel tasks')
    parser.add_argument('-p','--pause-between-operations', type = int, required = False, default = 1, metavar="PAUSE_BETWEEN_OPERATIONS", help='The pause in seconds between fetching and pulling each chart version')
    args = parser.parse_args()
    main(args.charts_file, args.num_parallel_tasks, args.pause_between_operations)
