
##configure cluster parameters
```shell
LOCATION=westus2 # Location 
AKS_NAME=aks-storage
RG=$AKS_NAME-$LOCATION
AKS_VNET_NAME=$AKS_NAME-vnet # The VNET where AKS will reside
AKS_CLUSTER_NAME=$AKS_NAME-cluster # name of the cluster
AKS_VNET_CIDR=172.16.0.0/16 #VNET address space
AKS_NODES_SUBNET_NAME=$AKS_NAME-subnet # the AKS nodes subnet name
AKS_NODES_SUBNET_PREFIX=172.16.0.0/23 # the AKS nodes subnet address space
SERVICE_CIDR=10.0.0.0/16
DNS_IP=10.0.0.10
NETWORK_PLUGIN=azure # use azure CNI 
NETWORK_POLICY=calico # use calico network policy
SYSTEM_NODE_COUNT=3 # system node pool size (single pool with 3 nodes across AZs)
USER_NODE_COUNT=2 # 3 node pools with 2 nodes each 
NODES_SKU=Standard_D4as_v4 #node vm type 
K8S_VERSION=$(az aks get-versions  -l $LOCATION --query 'orchestrators[-1].orchestratorVersion' -o tsv) #get latest GA k8s version 
SYSTEM_POOL_NAME=systempool
STORAGE_POOL_ZONE1_NAME=espoolz1
STORAGE_POOL_ZONE2_NAME=espoolz2
STORAGE_POOL_ZONE3_NAME=espoolz3
IDENTITY_NAME=$AKS_NAME`date +"%d%m%y"` # cluster managed identity
```

##Create resource group
```shell
az group create --name $RG --location $LOCATION
```

##create the cluster identity
```shell
az identity create --name $IDENTITY_NAME --resource-group $RG
```

##get the identity id and client id, we will use them later 
```shell
IDENTITY_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query id -o tsv)
IDENTITY_CLIENT_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query clientId -o tsv)
```

##Create the VNET and Subnet 
```shell
az network vnet create \
  --name $AKS_VNET_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --address-prefix $AKS_VNET_CIDR \
  --subnet-name $AKS_NODES_SUBNET_NAME \
  --subnet-prefix $AKS_NODES_SUBNET_PREFIX
  ```

##get the RG and VNET IDs
```shell
RG_ID=$(az group show -n $RG  --query id -o tsv)
VNETID=$(az network vnet show -g $RG --name $AKS_VNET_NAME --query id -o tsv)


##Assign the managed identity permissions on the RG and VNET
az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $RG_ID --role Contributor
az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $VNETID --role Contributor

##Validate Role Assignment
az role assignment list --assignee $IDENTITY_CLIENT_ID --all -o table

Principal                             Role         Scope
------------------------------------  -----------  -------------------------------------------------------------------------------------------------------------------------------------------------------
c068a2aa-02b2-40b1-ba2c-XXXXXXXXXXXX  Contributor  /subscriptions/SUBID/resourceGroups/aks-storage-westus2
c068a2aa-02b2-40b1-ba2c-XXXXXXXXXXXX  Contributor  /subscriptions/SUBID/resourceGroups/aks-storage-westus2/providers/Microsoft.Network/virtualNetworks/aks-storage-vnet

#get the subnet id 
AKS_VNET_SUBNET_ID=$(az network vnet subnet show --name $AKS_NODES_SUBNET_NAME -g $RG --vnet-name $AKS_VNET_NAME --query "id" -o tsv)
```

### create the cluster 
```shell
az aks create \
-g $RG \
-n $AKS_CLUSTER_NAME \
-l $LOCATION \
--node-count $SYSTEM_NODE_COUNT \
--node-vm-size $NODES_SKU \
--network-plugin $NETWORK_PLUGIN \
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
--zones 1 2 3 
```



### get the credentials 
```shell
az aks get-credentials -n $AKS_CLUSTER_NAME -g $RG

##validate nodes are running and spread across AZs
kubectl get nodes
NAME                                 STATUS   ROLES   AGE     VERSION
aks-systempool-26459571-vmss000000   Ready    agent   7d15h   v1.23.5
aks-systempool-26459571-vmss000001   Ready    agent   7d15h   v1.23.5
aks-systempool-26459571-vmss000002   Ready    agent   7d15h   v1.23.5

##check the system nodes spread over availaiblity zones 
kubectl describe nodes -l agentpool=systempool | grep -i topology.kubernetes.io/zone

                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-3
```
##now we need to add our node pools 

##First Node Pool in Zone 1
```shell
az aks nodepool add \
--cluster-name $AKS_CLUSTER_NAME \
--mode User \
--name $STORAGE_POOL_ZONE1_NAME \
--node-vm-size $NODES_SKU \
--resource-group $RG \
--zones 1 \
--enable-cluster-autoscaler \
--max-count 4 \
--min-count 2 \
--node-count $USER_NODE_COUNT \
--node-taints app=ealsticsearch:NoSchedule \
--labels dept=dev purpose=storage \
--tags dept=dev costcenter=1000 \
--no-wait

##Second Node Pool in Zone 2
az aks nodepool add \
--cluster-name $AKS_CLUSTER_NAME \
--mode User \
--name $STORAGE_POOL_ZONE2_NAME \
--node-vm-size $NODES_SKU \
--resource-group $RG \
--zones 2 \
--enable-cluster-autoscaler \
--max-count 4 \
--min-count 2 \
--node-count $USER_NODE_COUNT \
--node-taints app=ealsticsearch:NoSchedule \
--labels dept=dev purpose=storage \
--tags dept=dev costcenter=1000 \
--no-wait


##Third Node Pool in Zone 3
az aks nodepool add \
--cluster-name $AKS_CLUSTER_NAME \
--mode User \
--name $STORAGE_POOL_ZONE3_NAME \
--node-vm-size $NODES_SKU \
--resource-group $RG \
--zones 3 \
--enable-cluster-autoscaler \
--max-count 4 \
--min-count 2 \
--node-count $USER_NODE_COUNT \
--node-taints app=ealsticsearch:NoSchedule \
--labels dept=dev purpose=storage \
--tags dept=dev costcenter=1000 \
--no-wait


##it will take couple of minutes to add the nodes, validate that nodes are added to the cluster and spread correctly 
kubectl get nodes -l dept=dev

NAME                               STATUS   ROLES   AGE     VERSION
aks-espoolz1-21440163-vmss000000   Ready    agent   7d15h   v1.23.5
aks-espoolz1-21440163-vmss000001   Ready    agent   7d15h   v1.23.5
aks-espoolz2-14777997-vmss000000   Ready    agent   7d14h   v1.23.5
aks-espoolz2-14777997-vmss000001   Ready    agent   7d14h   v1.23.5
aks-espoolz3-54338334-vmss000000   Ready    agent   7d14h   v1.23.5
aks-espoolz3-54338334-vmss000001   Ready    agent   7d14h   v1.23.5


##Validate the zone distribution 
kubectl describe nodes -l dept=dev | grep -i topology.kubernetes.io/zone


                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-3
                    topology.kubernetes.io/zone=westus2-3

##the Nodepool name will be added to the "agentpool" label on the nodes 
kubectl describe nodes -l dept=dev | grep -i agentpool
```

## Deploy Elastic Search to the cluster  

##We start by creating our storage class 
```shell
cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: es-storageclass #storage class name
parameters:
  kind: Managed #we will use Azure managed disks
  storageaccounttype: Premium_LRS #use premium managed disk
  tags: costcenter=dev,app=elasticsearch  #add tags so all disks related to our application are tagged
provisioner: disk.csi.azure.com
reclaimPolicy: Retain #changed from default "Delete" to "Retain" so we can retain the disks even if the claim is deleted
volumeBindingMode: WaitForFirstConsumer #instrcuts the scheduler to wait for the pod to be scheduled before binding the disks
EOF
```
##Add the elastic search helm chart 
```shell
helm repo add bitnami https://charts.bitnami.com/bitnami

##check the possible values 
helm show values bitnami/elasticsearch > values_sample.yaml
```
##we will create our own values file (I left one in the repo as a sample that you can use here) where we will 
1. Adjust the affinity and taints to match our node pools 
2. configure the storage class 
3. optionally make the elastic search service accessible using a load balancer 

##create a name space for elastic search 
```shell
kubectl create namespace elasticsearch

#install elastic search using the values file 
helm install elasticsearch-v1 bitnami/elasticsearch -n elasticsearch --values values.yaml

#validate the installation, it will take around 5 minutes for all the pods to move to a "running state" 
kubectl get pods -o wide -n elasticsearch -w 


#check the service so we can access elastic search, note the "External-IP" 
kubectl get svc -n elasticsearch elasticsearch-v1


#lets store the value of the "elasticsearch-v1" service IP so we can use it later
esip=`kubectl get svc  elasticsearch-v1 -n elasticsearch -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'`
```

##Lets validate our deployment and insert some data 
#get the version 
```shell
curl -XGET "http://$esip:9200"

{
  "name" : "elasticsearch-v1-coordinating-1",
  "cluster_name" : "elastic",
  "cluster_uuid" : "kz5rkH_2T9W6u4sUPZE2oQ",
  "version" : {
    "number" : "8.2.0",
    "build_flavor" : "default",
    "build_type" : "tar",
    "build_hash" : "b174af62e8dd9f4ac4d25875e9381ffe2b9282c5",
    "build_date" : "2022-04-20T10:35:10.180408517Z",
    "build_snapshot" : false,
    "lucene_version" : "9.1.0",
    "minimum_wire_compatibility_version" : "7.17.0",
    "minimum_index_compatibility_version" : "7.0.0"
  },
  "tagline" : "You Know, for Search"
}


#check the cluster health and check the shards 
curl "http://$esip:9200/_cluster/health?pretty"

{
  "cluster_name" : "elastic",
  "status" : "green",
  "timed_out" : false,
  "number_of_nodes" : 18,
  "number_of_data_nodes" : 6,
  "active_primary_shards" : 5,
  "active_shards" : 10,
  "relocating_shards" : 0,
  "initializing_shards" : 0,
  "unassigned_shards" : 0,
  "delayed_unassigned_shards" : 0,
  "number_of_pending_tasks" : 0,
  "number_of_in_flight_fetch" : 0,
  "task_max_waiting_in_queue_millis" : 0,
  "active_shards_percent_as_number" : 100.0
}

#insert some data and make sure you use 3 shards and a replica 

curl -X PUT "$esip:9200/customer/_doc/1?pretty" -H 'Content-Type: application/json' -d'{
    "name": "kubecon",
    "settings" : {"index" : {"number_of_shards" : 3, "number_of_replicas" : 1 }}}'

#validate the inserted doc 
curl "$esip:9200/customer/_search?q=*&pretty"

{
  "took" : 58,
  "timed_out" : false,
  "_shards" : {
    "total" : 1,
    "successful" : 1,
    "skipped" : 0,
    "failed" : 0
  },
  "hits" : {
    "total" : {
      "value" : 1,
      "relation" : "eq"
    },
    "max_score" : 1.0,
    "hits" : [
      {
        "_index" : "customer",
        "_id" : "1",
        "_score" : 1.0,
        "_source" : {
          "name" : "kubecon",
          "settings" : {
            "index" : {
              "number_of_shards" : 3,
              "number_of_replicas" : 1
            }
          }
        }
      }
    ]
  }
}



#extra validations 
curl -X GET "$esip:9200/_cat/indices?v"

curl http://$esip:9200/_cat/shards/test\?pretty\=true
```


## Install Kasten 

#create an app registration for Kasten in azure active directory 
```shell
AZURE_SUBSCRIPTION_ID=$(az account list --query "[?isDefault][id]" --all -o tsv)

SP_NAME="mokasten"
AZURE_CLIENT_SECRET=`az ad sp create-for-rbac --name $SP_NAME --skip-assignment --query 'password' -o tsv`
AZURE_CLIENT_ID=`az ad sp list --display-name $SP_NAME --query '[0].appId' -o tsv`
AZURE_TENANT_ID="YOUR_AZURE_TENANT_ID"



##Assign the SP Permission to the subcription, this is done for simplicity only, you only need access to the resource groups where the cluster is and where the blob storage account will be 
az role assignment create --assignee $SP_CLIENT_ID  --role "Contributor"
az role assignment create --assignee $SP_CLIENT_ID  --role "User Access Administrator"
```
#now we need to create a snapshot configuration class for Kasten 
```shell
cat <<EOF | kubectl apply -f -
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
driver: disk.csi.azure.com
metadata:
  annotations:
    k10.kasten.io/is-snapshot-class: "true"
  name: csi-azure-disk-snapclass
deletionPolicy: Retain
EOF 
```
#run the pre checks 
```shell
curl https://docs.kasten.io/tools/k10_primer.sh | bash

#create a namespace for Kasten 
kubectl create namespace kasten-io

#add the helm repo and install 
helm repo add kasten https://charts.kasten.io/
helm repo update 

helm install k10 kasten/k10 --namespace=kasten-io \
  --set secrets.azureTenantId=$AZURE_TENANT_ID \
  --set secrets.azureClientId=$AZURE_CLIENT_ID \
  --set secrets.azureClientSecret=$AZURE_CLIENT_SECRET \
  --set global.persistence.metering.size=1Gi \
  --set prometheus.server.persistentVolume.size=1Gi \
  --set global.persistence.catalog.size=1Gi \
  --set global.persistence.jobs.size=1Gi \
  --set global.persistence.logging.size=1Gi \
  --set global.persistence.grafana.size=1Gi \
  --set auth.tokenAuth.enabled=true \
  --set externalGateway.create=true \
  --set metering.mode=airgap 
```
#validate 
```shell
kubectl get pods --namespace kasten-io

#get the service account token so you can use it to access the dashboard 
sa_secret=$(kubectl get serviceaccount k10-k10 -o jsonpath="{.secrets[0].name}" --namespace kasten-io)

kubectl get secret $sa_secret --namespace kasten-io -ojsonpath="{.data.token}{'\n'}" | base64 --decode


#access dashboard on localhost 
kubectl --namespace kasten-io port-forward service/gateway 8080:8000
```


##Create a storage account to ship the backed up files from Kasten to it 


#define variables 
```shell
DATE=$(date +%Y%m%d)
PREFIX=kastendemo
BACKUP_RG=kasten-backup-${LOCATION}
STORAGE_ACCOUNT_NAME=${PREFIX}${DATE}backup 

#create resource group 
az group create -n $BACKUP_RG -l $LOCATION

#create storage account 
az storage account create \
    --name $STORAGE_ACCOUNT_NAME \
    --resource-group $BACKUP_RG \
    --sku Standard_GRS \
    --encryption-services blob \
    --https-only true \
    --kind BlobStorage \
    --access-tier Hot


STORAGE_ACCOUNT_KEY=$(az storage account keys list -g $BACKUP_RG -n $STORAGE_ACCOUNT_NAME --query "[0].value" -o tsv)

#create blob container 
BLOB_CONTAINER=kasten
az storage container create -n $BLOB_CONTAINER --public-access off --account-name $STORAGE_ACCOUNT_NAME
```


#create secret for storage account 
```shell
AZURE_STORAGE_ENVIRONMENT=AzurePublicCloud
AZURE_STORAGE_SECRET=k10-azure-blob-backup

kubectl create secret generic $AZURE_STORAGE_SECRET \
      --namespace kasten-io \
      --from-literal=azure_storage_account_id=$STORAGE_ACCOUNT_NAME \
      --from-literal=azure_storage_key=$STORAGE_ACCOUNT_KEY \
      --from-literal=azure_storage_environment=$AZURE_STORAGE_ENVIRONMENT
```

#now create your backup policy 
```shell
cat <<EOF | kubectl apply -f -
kind: Profile
apiVersion: config.kio.kasten.io/v1alpha1
metadata:
  name: azure-backup-storage-location
  namespace: kasten-io
spec:
  locationSpec:
    type: ObjectStore
    objectStore:
      name: kasten
      objectStoreType: AZ
      region: $LOCATION
    credential:
      secretType: AzStorageAccount
      secret:
        apiVersion: v1
        kind: secret
        name: $AZURE_STORAGE_SECRET
        namespace: kasten-io
  type: Location
EOF
```



# create namespace and restore 

