# artifact-registry-helm-chart-synchronizer
Tools to create a curated private Helm chart repository in Artifact Registry and to keep it synchronized with its public sources.

https://cloud.google.com/artifact-registry/docs/helm/manage-charts

This repository contains:
* A containerized Python application that allows to scale GKE Standard cluster node pools.
* A Helm chart to deploy multiple Kubernetes Cronjobs, one per each schedule (Scale Up and Scale Down), per node pool, per cluster.
* A boostrapping script to create the GCP resoruces necessary to test the application.

## app/helm_chart_synchronizer.py

The script reads environment variables to determine the location of the Artifact Registry:
- A GCP Project ID
- A GCP Location (Region or Zone)

It then reads a YAML configuration file that must be passed as an argument, which details a series of Helm charts to be pulled, their source locations and destination repositories within Artifact Registry.

The scripts accepts a second optional argument to define the level of parallelism. It is either the number of Helm charts in the file or 10, whichever is lowest.

### Testing Python Application locally

This application can be run using Python **3.10** or higher.

A test file called [example_charts.yaml](./app/example_charts.yaml) is included in this repository.

Follow these steps to execute the script locally:

```
# Configure the required environment variables
export ARTIFACT_REGISTRY_PROJECT_ID=test-project
export ARTIFACT_REGISTRY_HOSTNAME=us-east1-b.pkg.dev
export DEBUG=false

# Move into the application directory
cd app/

# Create a Python Virtual Environment
python -m venv poc-venv

# Activate the Virtual Environment
source poc-venv/bin/activate

# Install the requirements
python -m pip install -r <path-to>/requirements.txt

# Make sure you're authenticated against Google Cloud
gcloud auth login

* Execute the script, passing the charts file as an argument
python helm_chart_synchronizer.py example_charts.yaml
```

## Bootstrapping the Proof of Concept environment

The repository includes a few helper scripts to deploy a Proof-of-Concept environment to test the application.
These are better run from a `Google Cloud Shell` session since it contains all the required tools.

1. `bootstrap.sh` - Will set everything up, and may also build and push the container image to the Artifact Registry repository.

2. `build.sh` - Builds the container image without running the whole bootstrapping process.

3. Once the environment is up and running, and the image has been built, you may deploy the application using Helm as shown in the at the bottom of the page.

### bootstrap.sh

This script will bootstrap a Proof of Concept environment that allows to test this solution with minimal cost.
In detail, it:

- Creates a GCP project.
- Enables Billing for the project.
- Enables the necessary GCP Services (GKE, Artifact Registry).
- Creates a GCP Service Account (GSA).
- Grants permissions to the GSA.
- Creates and Artifact Registry repository.
- Creates a GKE Cluster with Workload Identity enabled and 4 node pools:
  - default-pool, for system workloads.
  - spot-pool, where the node pool scaling cronjobs will run.
- Create a Kubernetes Service Account in the application namespace.
- Binds the GSA and KSA to leverage Workload Identity.
- Grants permissions to the GSA on Artifact Registry.
- Optionally builds and pushes the container image for the node-pool scaler application.

Usage:
```
./bootstrap.sh PROJECT_ID ZONE BILLING_ACCOUNT CLUSTER_NAME APP_NAME REPO_NAME [ --build-and-push-image [TAG] ]
```

Example:
```
./bootstrap.sh test-project us-east1-b A11BB-123ABCD-BCD321 cluster-1 helm-chart-synchronizer testrepo --build-and-push-image 1.0.0
```

### build.sh

If `docker` is installed on your workspace, this script will build and push the container image for the node-pool scaler application.

Usage:
```
./build.sh REPOSITORY_PATH IMAGE_NAME TAG
```

Example:
```
./build.sh us-east1-docker.pkg.dev/test-project/testrepo helm-chart-synchronizer 1.0.0
```

## Helm Chart

The Helm Chart contained in this repository creates as many Kubernetes CronJobs as Node Pool scaling schedules are defined in the VALUES file.

### Rendering the templates

To render the Helm templates locally, from the **root** of this repository, execute the following command:

```
mkdir -p rendered && helm template --debug -f <VALUES-FILE-NAME>.yaml . > rendered/<RENDERED-TEMPLATE-NAME>.yaml
```

### Installing the Chart in the GKE cluster

[Install the Helm CLI](https://helm.sh/docs/intro/install/#from-script) if it is not present on your workspace.

Authenticate against Google Cloud:

```
gcloud auth login
```

Authenticate against the cluster:

```
gcloud container clusters get-credentials CLUSTER_NAME --project PROJECT_ID --location REGION_OR_ZONE
```

To install the release and create the Cronjobs in the selected Namespace, execute the following command from the **root** of this repository:

```
helm install RELEASE_NAME . --namespace NAMESPACE --values <VALUES-FILE-NAME>.yaml
```

To update the release, change any values or edit the templates and execute the following command from the **root** of this repository:

```
helm upgrade RELEASE_NAME . --namespace NAMESPACE --values <VALUES-FILE-NAME>.yaml
```
