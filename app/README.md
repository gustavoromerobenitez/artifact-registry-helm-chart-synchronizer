# helm-chart-synchronizer Python App

## app/helm_chart_synchronizer.py

The script reads environment variables to determine the location of the Artifact Registry:
- A GCP Project ID
- A GCP Location (Region or Zone)

It then reads a YAML configuration file that must be passed as an argument, which details a series of Helm charts to be pulled, their source locations and destination repositories within Artifact Registry.

The script accepts a second optional argument to define the level of parallelism. It is either the number of Helm charts in the file or 10, whichever is lowest.

### Registry Certificate Verification

The script will attempt to verify the certificates presented by the remote **source** registries if there is a subdirectory called **trusted-signer-certs**.

Most public registries are signed by well known CAs and their signer certificates are publicly available. All you need to do is to concat them into a file and put it in the `app/trusted-signer-certs directory`.

Should you need to trust a private registry. you can either add the CA signer certificates to the above file, or you can trust only the regsitry cerificate directly.

In order to pull the certificate from the private repository, you may use the `openssl` CLI. For example, this code will write the leaf certificate of charts.jetstack.io into a local file:

```
openssl s_client -connect charts.jetstack.io:443 -showcerts < /dev/null 2>/dev/null | openssl x509 -outform PEM > app/trusted-signer-certificates/charts_jetstack_io.pem
```

### Registry Authentication




## SAST Tools included

### Trivy CLI

### Checkov


### Testing Python Application locally

This application can be run using Python **3.10** or higher.

A test file called [example_charts.yaml](./app/example_charts.yaml) is included in this repository.

Follow these steps to execute the script locally:

```
# Configure the required environment variables
export ARTIFACT_REGISTRY_PROJECT_ID=test-project
export ARTIFACT_REGISTRY_HOSTNAME=us-east1-docker.pkg.dev
export VERIFY_CERTIFICATES=false
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
