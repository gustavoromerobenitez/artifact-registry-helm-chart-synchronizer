# Helm Chart

The Helm Chart contained in this repository creates a Kubernetes CronJob that runs the [helm-chart-synchronizer](./app/README.md) Python App on a schedule.

## Overview of configuration

### Concurency control

You can control how many worker processes will be spawned to split the work of processing the Helm charts. An optional pause allows you to throttle the execution of the application. This is useful to avoid overwhelming network elements like proxies with too many concurrent requests, which might result in requests being dropped.

```yaml
numParallelTasks: 4
pauseBetweenOperations: 1
```

### Static Code Analysis of the Infrastructure-as-Code

You can enable or disable the SAST tools included, as well as configure the GCS bucket that will store the reports, via the following configuration keys:

```yaml
sast:
  bucketName: my-compliance-reporting-bucket
  runTrivy: true
  runCheckov: true
```

## Source Registry Certificate Verification

It is possible to configure source registry certificate verification either by using an existing secret or by creating a new secret.
This feature can only be turned on or off for all registries at once, hence you need to make sure to include all certificate signers in bundle inside the secret.

To create a certificate bundle file, you can use a command like this:

```bash
cat signer-certificate-file-1.pem signer-certificate-2.pem other.pem > ca-bundle.pem
```

Lastly, configure the certificate bundle path in the values.yaml file:

```yaml
verifyRegistryCertificates:
  createSecret:
    name: trusted-signers
    relativePathToCertificatesBundle: app/trusted-signer-certs/ca-bundle.pem
```

## Source Registry Authentication

This feature can be enabled individually for each applicable registry and separate secrets can be provided for each registry.

Add a key for each registry under `authenticatedRegistries` and indicate the secret names for the username and password.

Those secrets should be declared in JSON format and you should also indicate the key that contains the value for username or password respectively. For example:

```yaml
authenticatedRegistries:
  authenticated-registry-1.dummyorg.fake:
    usernameSecret: authenticated-registry-1-secret
    usernameSecretKey: username
    passwordSecret: authenticated-registry-1-secret
    passwordSecretKey: password
```

### Rendering the templates

To render the Helm templates locally, from the **root** of this repository, execute the following command:

```bash
mkdir -p rendered && helm template --debug -f <VALUES-FILE-NAME>.yaml . > rendered/<RENDERED-TEMPLATE-NAME>.yaml
```

### Installing the Chart in the GKE cluster

[Install the Helm CLI](https://helm.sh/docs/intro/install/#from-script) if it is not present on your workspace.

Authenticate against Google Cloud:

```bash
gcloud auth login
```

Authenticate against the cluster:

```bash
gcloud container clusters get-credentials CLUSTER_NAME --project PROJECT_ID --location REGION_OR_ZONE
```

To install the release and create the Cronjobs in the selected Namespace, execute the following command from the **root** of this repository:

```bash
helm install RELEASE_NAME . --namespace NAMESPACE --values <VALUES-FILE-NAME>.yaml
```

To update the release, change any values or edit the templates and execute the following command from the **root** of this repository:

```bash
helm upgrade RELEASE_NAME . --namespace NAMESPACE --values <VALUES-FILE-NAME>.yaml
```