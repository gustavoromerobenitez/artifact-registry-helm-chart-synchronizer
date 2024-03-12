# artifact-registry-helm-chart-synchronizer
Tools to create a curated private Helm chart repository in Artifact Registry and to keep it synchronized with its public sources.

https://cloud.google.com/artifact-registry/docs/helm/manage-charts


## Testing the script locally

* Create a python virtual environment:  

```
python -m venv virtualenv
```

* Activate the virtual environment:  

```
source virtualenv/bin/activate
```

* Install the pre-requisite packages:  

```
python -m pip install -r requirements.txt
```


* Get a service account key with permissions to write to Artifact Registry, for instance, generate a key for the tekton-pipelines-sa Service Account and download it as a JSON file.

* Set the environment variables:

```
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
export PATH="${BASE_DIR}/artifact-registry-helm-chart-synchronizer:$PATH"
```

* Activate the service account

```
gcloud auth activate-service-account --key-file=${GOOGLE_APPLICATION_CREDENTIALS}
```

* Use a test [charts.yaml](./charts.yaml) file to test the script

* Run the script:

```
python helm-charts-synchronizer.py charts.yaml
```

