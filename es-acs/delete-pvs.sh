#!/bin/bash

# List all PVC names and delete them
pvc_names=$(kubectl get pvc -n elasticsearch -o custom-columns=":metadata.name" --no-headers)

for pvc_name in $pvc_names; do
    namespace=elasticsearch
    kubectl delete pvc $pvc_name -n $namespace
done