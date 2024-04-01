# helm-chart-synchronizer Python App

## app/helm_chart_synchronizer.py

The script reads a YAML configuration file which, by default, is [charts.yaml](./config/charts.yaml). This file should contain a **list** of Helm charts to be pulled, their source locations and their destination repositories within Artifact Registry.

```yaml
charts:
- registry: https://oauth2-proxy.github.io/manifests
  repository: oauth2-proxy
  chart: oauth2-proxy
  destination_repository: testrepo
  versions:
  - 7.1.0
```

The script also accepts:
- A second optional argument to define the level of parallelism. Its default value will be either the number of Helm charts in the file or 10, whichever is lowest.
- A third argument which determines the pause, in seconds, to be made after every helm operation, thus throttling the execution of the script. This is useful to avoid overwhelming network elements like proxies with too many concurrent requests, which might result in requests being dropped.

For each chart, it will pull each version indicated in the configuration. Then it may *optionally* analyze it with SAST tools and store the reports in a GCS bucket, and lastly it will push the chart in OCI format to the target Artifact Registry repository. 

## Registry Certificate Verification

The script will attempt to verify the certificates presented by the remote **source** registries if there is a subdirectory called **trusted-signer-certs**.

Most public registries are signed by well known CAs and their signer certificates are publicly available. All you need to do is to concat them into a **PEM** file and put it in the [app/trusted-certs](./trusted-certs) directory.

In order to pull the certificate from the remote repository, you may use the `openssl` CLI. For example, this code will write the leaf certificate of `charts.jetstack.io` into a local file:

```bash
openssl s_client -connect charts.jetstack.io:443 -showcerts < /dev/null 2>/dev/null | openssl x509 -outform PEM > app/trusted-certs/charts_jetstack_io.pem
```

To create a certificate bundle file, you can use a command like this:

```bash
cat signer-certificate-file-1.pem signer-certificate-2.pem other.pem > ca-bundle.pem
```

Should you need to trust a private registry. you can either add the CA signer certificates to the above file, or you can trust only the registry certificate directly.

## Registry Authentication

If any of the source registries listed under `charts` in [charts.yaml](./config/charts.yaml) requires authentication, it should be declared separately under the key `authenticatedRegistries` in the same file. Simply add the domain names of those registries and the script will try and locate their credentials in environment variables named after the repositories' domain names.

```yaml
authenticatedRegistries:
  - authenticated-registry-1.dummyorg.fake
  - authenticated-registry-2.dummyorg.fake
```

```bash
# Environment variables that the script would expect
AUTHENTICATED_REGISTRY_1_DUMMYORG_FAKE_USERNAME=<the1stusername>
AUTHENTICATED_REGISTRY_1_DUMMYORG_FAKE_PASSWORD=<the1stpasswordorPAT>
AUTHENTICATED_REGISTRY_2_DUMMYORG_FAKE_USERNAME=<the2ndusername>
AUTHENTICATED_REGISTRY_2_DUMMYORG_FAKE_PASSWORD=<the2ndpasswordororPAT>
```

## SAST Tools execution

The script can optionally invoke [Checkov](https://www.checkov.io/) and/or [Trivy](https://trivy.dev/) for every Helm chart that it pulls from its source, generate a compliance report and upload it to a GCS bucket.

These behaviours are enabled or disabled via the environment variables `RUN_TRIVY` and `RUN_CHECKOV`, which accept boolean like values: `1, 0, y, n, yes, no, [Tt]rue, [Ff]alse`.
The value of the variable `BUCKET_URL` should be a Cloud Storage bucket URL, i.e.: `gs://<BUCKET_NAME>`.

## Testing Python Application locally

This application requires Python **3.11** or higher.

The configuration file is called [charts.yaml](./config/charts.yaml) and contains a few chart references for demonstration purposes.

Follow these steps to execute the script locally:

```bash
export ARTIFACT_REGISTRY_PROJECT_ID=test-project
export ARTIFACT_REGISTRY_HOSTNAME=us-east1-docker.pkg.dev
export VERIFY_CERTIFICATES=false
export DEBUG=false

# Configure the following optional variables if you want to run the Static Analysis Tools (SAST)
export BUCKET_URL=gs://my-reporting-bucket
export RUN_TRIVY=True
export RUN_CHECKOV=True

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
