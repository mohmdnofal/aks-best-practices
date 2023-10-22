# Introduction

This repo contains the code and instructions to deploy an Elastic Search cluster on Azure Kubernetes Service (AKS) using Azure Container Storage (ACS) as the storage backend. 

below are the steps in high level
1. create AKS cluster with 2 pools (one system and one user pool)
2. both pools will be deployed in a single AZ for demo purposes with autoscaling enabled 
3. deploy azure container storage on the cluster
4. deploy elastic search using helm chart
  - all components are deployed with autoscaling enabled 
  - master and data nodes have persistence enabled and they will consume from the storage pool we created in step 3

5. ingest data into elastic search using python script in a docker image which will be deployed as a kubernetes job
6. as the data being ingested watch the pods scale in and out and the data being redistributed across the nodes


# Cluster Create 

```bash
LOCATION=northeurope # Location 
AKS_NAME=aks-es-acs
RG=$AKS_NAME-$LOCATION-rg
AKS_VNET_NAME=$AKS_NAME-vnet # The VNET where AKS will reside
AKS_CLUSTER_NAME=$AKS_NAME # name of the cluster
AKS_VNET_CIDR=172.16.0.0/16
AKS_NODES_SUBNET_NAME=$AKS_NAME-subnet # the AKS nodes subnet
AKS_NODES_SUBNET_PREFIX=172.16.0.0/23
SERVICE_CIDR=10.0.0.0/16
DNS_IP=10.0.0.10
NETWORK_PLUGIN=azure # use Azure CNI 
SYSTEM_NODE_COUNT=5  # system node pool size 
USER_NODE_COUNT=6 # change this to match your needs
NODES_SKU=Standard_D8ds_v4 # node VM type (change this to match your needs)
K8S_VERSION=1.27
SYSTEM_POOL_NAME=systempool
STORAGE_POOL_ZONE1_NAME=espoolz1
IDENTITY_NAME=$AKS_NAME`date +"%d%m%y"`
```



### Create the resource group
```bash
az group create --name $RG --location $LOCATION
```

### create identity for the cluster 
We're going to reuse the cluster identity created below for simplicity, but in a real world scenario you may prefer to maintain separate identities.

```bash
az identity create --name $IDENTITY_NAME --resource-group $RG
```

### get the identity id and clientid, we will use them later 
```bash
IDENTITY_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query id -o tsv)
IDENTITY_CLIENT_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query clientId -o tsv)
```

### Create the VNET and Subnet 
```bash
az network vnet create \
  --name $AKS_VNET_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --address-prefix $AKS_VNET_CIDR \
  --subnet-name $AKS_NODES_SUBNET_NAME \
  --subnet-prefix $AKS_NODES_SUBNET_PREFIX
```

### get the RG, VNET, and Subnet IDs
RG_ID=$(az group show -n $RG  --query id -o tsv)
VNETID=$(az network vnet show -g $RG --name $AKS_VNET_NAME --query id -o tsv)
AKS_VNET_SUBNET_ID=$(az network vnet subnet show --name $AKS_NODES_SUBNET_NAME -g $RG --vnet-name $AKS_VNET_NAME --query "id" -o tsv)

### Assign the managed identity permissions on the RG and VNET
> *NOTE:* For the purposes of this demo we are setting the rights as highly unrestricted. You will want to set the rights below to meet your security needs.
```bash
az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $RG_ID --role Contributor
az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $VNETID --role Contributor
```

### Validate Role Assignment
```bash
az role assignment list --assignee $IDENTITY_CLIENT_ID --all -o table
```


### create the cluster 
```bash
az aks create \
-g $RG \
-n $AKS_CLUSTER_NAME \
-l $LOCATION \
--node-count $SYSTEM_NODE_COUNT \
--node-vm-size $NODES_SKU \
--network-plugin $NETWORK_PLUGIN \
--network-plugin-mode overlay \
--kubernetes-version $K8S_VERSION \
--generate-ssh-keys \
--service-cidr $SERVICE_CIDR \
--dns-service-ip $DNS_IP \
--vnet-subnet-id $AKS_VNET_SUBNET_ID \
--enable-addons monitoring \
--enable-managed-identity \
--assign-identity $IDENTITY_ID \
--nodepool-name $SYSTEM_POOL_NAME \
--uptime-sla \
--zones 1 
```



### get the credentials 
```bash
az aks get-credentials -n $AKS_CLUSTER_NAME -g $RG

##validate nodes are running and spread across AZs
kubectl get nodes -o wide

kubectl describe nodes | grep -i topology.kubernetes.io/zone
```

## Add a user node pool 

We will create a single node pool in 1 AZ to demonstrate scaling, we will add labels and use affinity to ensure only elastic search pods land on the node pool.
Also note that we add the "acstor.azure.com/io-engine=acstor" label so we can install Azure Container Storage later. 

```bash
##First Node Pool in Zone 1
az aks nodepool add \
--cluster-name $AKS_CLUSTER_NAME \
--mode User \
--name $STORAGE_POOL_ZONE1_NAME \
--node-vm-size $NODES_SKU \
--resource-group $RG \
--zones 1 \
--enable-cluster-autoscaler \
--max-count 12 \
--min-count 6 \
--node-count $USER_NODE_COUNT \
--labels app=es acstor.azure.com/io-engine=acstor 



##it will take couple of minutes to add the nodes, validate that nodes are added to the cluster and spread correctly 
kubectl get nodes -l app=es                                    

kubectl describe nodes -l dept=dev | grep -i topology.kubernetes.io/zone
```


# Deploy Azure Container Storage

```bash

##assign contributor role to AKS managed identity 

SUB_ID=$(az account show --query id --output tsv) 
export AKS_MI_OBJECT_ID=$(az aks show --name $AKS_CLUSTER_NAME --resource-group $RG --query "identityProfile.kubeletidentity.objectId" -o tsv)
az role assignment create --assignee $AKS_MI_OBJECT_ID --role "Contributor" --scope "/subscriptions/$SUB_ID"


##install azure container storage 
az k8s-extension create \
--cluster-type managedClusters \
--cluster-name $AKS_CLUSTER_NAME \
--resource-group $RG \
--name aksacs \
--extension-type microsoft.azurecontainerstorage \
--scope cluster \
--release-train stable \
--release-namespace acstor

##validate the extension is installed

az k8s-extension list --cluster-name $AKS_CLUSTER_NAME --resource-group $RG --cluster-type managedClusters

#create 1TB storage pool 
kubectl apply -f acstor-storagepool.yaml
kubectl describe sp azuredisk -n acstor
kubectl get sc acstor-azuredisk

```
# Deploy Elastic Search

## Elastic Search Cluster Setup
Its time to deploy our ElasticSearch Cluster to the Azure Kubernetes Service Cluster we just created. ElasticSearch has 3 main components that make up the cluster Client/Coordinating, Masters, and Data Nodes. you can read more about what each one does in elastic [public docs](https://www.elastic.co/guide/index.html).

1. **Client/Coordinating Nodes** Act as a reverse proxy for the clusters, this is what the external world interacts with. its deployed as a k8s deployment with horizontal pod autoscaling enabled, we will try to have a client in each node to minimize data movement across nodes, we can minimize but we can't prevent it from happening. 
2. **Master Nodes** stores the metadata about the data nodes, it will be deployment as a k8s deployment, ideally we need 3. 
3. **Data Nodes** this is where the magic is, this is where the indices are stored and replicated. this would be our Statefulset with persistent volume to persist the data.


## Elastic Search Cluster Installation 

### Prepare The Cluster 
We will use the "acstor-azuredisk" storage class 


## We will use helm to install the ElasticSearch cluster, we will rely on the ElasticSearch chart provided by bitnami as its the easiest one to navigate. 

## add the bitnami repository
```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
```
## Get the values file we'll need to update 
```shell
helm show values bitnami/elasticsearch > values_sample.yaml
```

We will create our own values file (there is a sample (values_acs.yaml) in this repo you can use) where we will 

1. Adjust the affinity and taints to match our node pools 
2. adjust the number of replicas and the scaling parameters for master, data, and coordinating, and ingestion nodes
3. configure the storage class 
4. optionally make the elastic search service accessible using a load balancer 
5. enable HPA for all the nodes 
   

### ElasticSearch Cluster Deployment

Now that we have configured the charts, we are ready to deploy the ES cluster 

```bash
# Create the namespace
kubectl create namespace elasticsearch

# Install elastic search using the values file 
helm install elasticsearch-v1 bitnami/elasticsearch -n elasticsearch --values values_acs.yaml

# Validate the installation, it will take around 5 minutes for all the pods to move to a 'READY' state 
watch kubectl get pods -o wide -n elasticsearch


# Check the service so we can access elastic search, note the "External-IP" 
kubectl get svc -n elasticsearch elasticsearch-v1
```


## Lets store the value of the "elasticsearch-v1" service IP so we can use it later
```bash
esip=`kubectl get svc  elasticsearch-v1 -n elasticsearch -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'`

export SERVICE_IP=$(kubectl get svc --namespace elasticsearch elasticsearch-v1 --template "{{ range (index .status.loadBalancer.ingress 0) }}{{ . }}{{ end }}")

curl http://$SERVICE_IP:9200/
```

## create an index 
```bash
##create an index called "acstor" with 3 replicas 
curl -X PUT "http://$esip:9200/acstor" -H "Content-Type: application/json" -d '{
  "settings": {
    "number_of_replicas": 3
  }
}'

##test the index 
curl -X GET "http://$esip:9200/acstor"
```


## ingest some data in elasticsearch using python 

```bash
cd dockerimage/

##build the image (change the image name to match your repo)
docker login

#change repo name to match yours (also use ACR instead of dockerhub)
docker build -t mohamman/my-ingest-image:1.0 .

docker push mohamman/my-ingest-image:1.0

##run the job (remember to change the image name to yours) also change the parallelism and completions to match your needs
cd ..
kubectl apply -f ingest-job.yaml

##to verify the job is running
kubectl get pods -l app=log-ingestion 
kubectl logs -l app=log-ingestion -f 


##watch the elastic search pods being scaled out 
watch kubectl get pods -n elasticsearch
kubectl get hpa -n elasticsearch 
```
