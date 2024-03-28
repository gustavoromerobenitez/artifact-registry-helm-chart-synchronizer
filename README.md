# artifact-registry-helm-chart-synchronizer
Tools to create a curated private Helm chart repository in Artifact Registry and to keep it synchronized with its public sources.

Reference:
- [https://cloud.google.com/artifact-registry/docs/helm/manage-charts]
- [https://helm.sh/docs/topics/registries/]

This repository contains:
* A [Python application](./app/README.md)that pulls Helm charts from multiple sources and pushes them to Artifact Registry repositories.
* A [Dockerfile](./Dockerfile) to containerize the application, which includes SAST tools to analyze the charts before they are pushed to Artifact Registry.
* An adittional [Dockerfile](./Dockerfile-without-SAST) to containerize the application, without SAST tools.
* A [Helm chart](./README_HELM.md) to deploy a Kubernetes Cronjob that would run the containerized application on a schedule.
* A [bootstrapping shell script](./bootstrap.sh) to create the GCP resources necessary to build, install and test the application.
* A [build script](./build.sh) that simplifies the process of building the container images locally.

## SAST Tools

The default [Dockerfile](./Dockerfile) includes two SAST tools, [Checkov](#checkov) and [Trivy](#trivy), which will be executed on every pulled Helm chart before these are uploaded to Artifact Registry.

Optionally, the user will be able to configure whether the process should fail if any Critical vulnerabilities are detected.

They both generate reports that will be saved and uploaded to a *GCS bucket*. These reports are useful to asses the Security Posture of the environment, as well as a potential requirements for compliance and audit puposes.

### Checkov

[Checkov](https://www.checkov.io/) is an open source Static Code Analysis Tool (SAST) for scanning Infrastructure as Code (IaC) files for security or compliance problems. It is also called a **Policy-as-Code** tool.

It [supports many IaC formats](https://www.checkov.io/1.Welcome/What%20is%20Checkov.html#supported-iac-types), including Helm.

### Trivy

[Trivy](https://trivy.dev/) is an open source Security Scanning tool which supports [a wide range of languages, pakages and configuration files](https://aquasecurity.github.io/trivy/v0.50/docs/coverage/) including [Helm templates](https://aquasecurity.github.io/trivy/v0.50/docs/coverage/iac/helm/).

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
