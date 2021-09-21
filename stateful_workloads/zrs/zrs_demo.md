# Azure Kubernetes Service (AKS) and Zone Redundant Disks (ZRS)

[Zone Redundant Disks](https://docs.microsoft.com/en-us/azure/virtual-machines/disks-redundancy#zone-redundant-storage-for-managed-disks) offers the ability to synchronously replicate your Azure Disk across 3 availability zones in an automated fashion. ZRS Disks are very beneficial for applications which don't support application level synchronous writes such as MongoDB and ElasticSearch. So if you have a single stateful application server/pod which you need to increase its availability by using availability zones, ZRS would come in handy. another use case for ZRS is [shared disks](https://docs.microsoft.com/en-us/azure/virtual-machines/disks-shared) which would be covered in future sections. 


# Demo Introduction 
In this demo we will create a 3 nodes cluster distributed across 3 availability zones, we will deploy a single mysql pod, ingest some data there, and then delete the node hosing the pod. This affectively means that we took one availability zone offline, this will trigger the Kubernetes scheduler to migrate your pod to another availability zone, with the help of ZRS we will be able to get access to the same disk in the new AZ. for completeness we will also use Velero to backup/restore the disk. 

By default azure disk is using locally redundant storage/disk which is a zonal resource, so in the above example, if LRS was in use the pod will be migrated to a new zone but it will fail to start as it will keep waiting for the disk which is a zonal resource.

# Demo

1. Create the cluster 
```shell 

#Set the parameters
LOCATION=northeurope # Location 
AKS_NAME=az-zrs
RG=$AKS_NAME-$LOCATION
AKS_CLUSTER_NAME=$AKS_NAME-cluster # name of the cluster
K8S_VERSION=$(az aks get-versions  -l $LOCATION --query 'orchestrators[-1].orchestratorVersion' -o tsv)


##Create RG
az group create --name $RG --location $LOCATION


## create the cluster 
az aks create \
-g $RG \
-n $AKS_CLUSTER_NAME \
-l $LOCATION \
--kubernetes-version $K8S_VERSION \
--zones 1 2 3 \
--generate-ssh-keys 


## get the credentials 

az aks get-credentials -n $AKS_CLUSTER_NAME -g $RG

## test

kubectl get nodes  

NAME                                STATUS   ROLES   AGE   VERSION
aks-nodepool1-20996793-vmss000000   Ready    agent   77s   v1.21.2
aks-nodepool1-20996793-vmss000001   Ready    agent   72s   v1.21.2
aks-nodepool1-20996793-vmss000002   Ready    agent   79s   v1.21.2
```

2. Verify CSI by checking your storage classes.

```shell
## as of K8s 1.21 CSI became the default in storage drivers, same in AKS, you can see the default storage class now pointing to azure disk CSI driver 

kubectl get storageclasses.storage.k8s.io 

NAME                    PROVISIONER                RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
azurefile               kubernetes.io/azure-file   Delete          Immediate              true                   2m30s
azurefile-csi           file.csi.azure.com         Delete          Immediate              true                   2m30s
azurefile-csi-premium   file.csi.azure.com         Delete          Immediate              true                   2m30s
azurefile-premium       kubernetes.io/azure-file   Delete          Immediate              true                   2m30s
default (default)       disk.csi.azure.com         Delete          WaitForFirstConsumer   true                   2m30s
managed                 kubernetes.io/azure-disk   Delete          WaitForFirstConsumer   true                   2m30s
managed-csi-premium     disk.csi.azure.com         Delete          WaitForFirstConsumer   true                   2m30s
managed-premium         kubernetes.io/azure-disk   Delete          WaitForFirstConsumer   true                   2m30s
```

3. Provision ZRS storage classes 

#this is based on this guide [here](https://github.com/kubernetes-sigs/azuredisk-csi-driver/blob/master/docs/install-driver-on-aks.md#option2-enable-csi-driver-on-existing-cluster)
```shell 
## Create ZRS storage class 
kubectl apply -f zrs-storageclass.yaml
##validate 
kubectl get storageclasses.storage.k8s.io zrs-class -o yaml 
```
```yaml
allowVolumeExpansion: true
apiVersion: storage.k8s.io/v1
kind: StorageClass
  name: zrs-class
parameters:
  skuname: Premium_ZRS
provisioner: disk.csi.azure.com
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
```


4. Create mysql statefulset using the ZRS volumes 
- This deployment is based on [this guide](https://kubernetes.io/docs/tasks/run-application/run-replicated-stateful-application/)
- The PVC was modified to consume disks from the zrs-class

```shell 
## create the configmap 
kubectl apply -f mysql-configmap.yaml

## create the headless service 
kubectl apply -f mysql-services.yaml

## create the statefulset 
kubectl apply -f mysql-statefulset.yaml

## check that 2 services were created (headless one for the statefulset and mysql-read for the reads) 
kubectl get svc -l app=mysql  

NAME         TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
mysql        ClusterIP   None           <none>        3306/TCP   5h43m
mysql-read   ClusterIP   10.0.205.191   <none>        3306/TCP   5h43m

## check the deployment (wait a bit until its running)
kubectl get pods -l app=mysql --watch

NAME      READY   STATUS    RESTARTS   AGE
mysql-0   2/2     Running   0          6m34s
```

- now that the DB is running lets inject some data so we later can simulate failures
```shell 
## create a database called zrstest and a table called "messages", then inject a record in the database 

kubectl run mysql-client --image=mysql:5.7 -i --rm --restart=Never --\
  mysql -h mysql-0.mysql <<EOF
CREATE DATABASE zrstest;
CREATE TABLE zrstest.messages (message VARCHAR(250));
INSERT INTO zrstest.messages VALUES ('Hello from ZRS');
EOF

## vaildata the data exist 
kubectl run mysql-client --image=mysql:5.7 -i -t --rm --restart=Never --\
  mysql -h mysql-read -e "SELECT * FROM zrstest.messages"

+----------------+
| message        |
+----------------+
| Hello from ZRS |
+----------------+
pod "mysql-client" deleted
```

5. Simulate failure by deleting an availability zone 

```shell 
## when we created our cluster we activated the availability zones feature, as we created 3 nodes, we should see that they are equally split across AZs 
kubectl describe nodes | grep -i topology.kubernetes.io/zone

                    topology.kubernetes.io/zone=northeurope-1
                    topology.kubernetes.io/zone=northeurope-2
                    topology.kubernetes.io/zone=northeurope-3

## lets check in which node our pods is running 
kubectl get pods -l app=mysql -o wide 
NAME      READY   STATUS    RESTARTS   AGE   IP           NODE                                NOMINATED NODE   READINESS GATES
mysql-0   2/2     Running   0          17m   10.244.2.4   aks-nodepool1-20996793-vmss000001   <none>           <none>

## We can see that the pod is running in "aks-nodepool1-20996793-vmss000001", deleting this node effecitvly means we are taking an availability zone offline, so lets try this out 

kubectl delete nodes aks-nodepool1-20996793-vmss000001

node "aks-nodepool1-20996793-vmss000001" deleted
```

##At this moment our statefulset should try to restart in a different node in a new zone, you would need to wait for ~8 minutes for the pod to start fully in the new nodes, the 8 minutes is driven by an upstream behavior which is explained [here](https://github.com/kubernetes-sigs/azuredisk-csi-driver/tree/master/docs/known-issues/node-shutdown-recovery)

```shell 
kubectl get pods -l app=mysql --watch -o wide
....
NAME      READY   STATUS    RESTARTS   AGE   IP           NODE                                NOMINATED NODE   READINESS GATES
mysql-0   2/2     Running   0          10m   10.244.0.7   aks-nodepool1-20996793-vmss000002   <none>           <none>

## now that the pods started, lets validate the ZRS magic, we should see the data we injected originally in the pod
kubectl run mysql-client --image=mysql:5.7 -i -t --rm --restart=Never --\
  mysql -h mysql-read -e "SELECT * FROM zrstest.messages"


+----------------+
| message        |
+----------------+
| Hello from ZRS |
+----------------+
pod "mysql-client" deleted

## This showcase the power of using ZRS disks 
```

6. For completeness in order to protect from incidentally deleting disks or full cluster failure, we will use Velero to backup and restore our statefulset. 

- Velero is a native kubernetes backup and restore application, the following demo is based on [this guide](https://github.com/vmware-tanzu/velero-plugin-for-microsoft-azure)

```shell

#Define the variables on where you need to back up and restore your volumes 
AZURE_BACKUP_SUBSCRIPTION_NAME='Microsoft Azure Internal Consumption'
AZURE_BACKUP_SUBSCRIPTION_ID=$(az account list --query="[?name=='$AZURE_BACKUP_SUBSCRIPTION_NAME'].id | [0]" -o tsv)
AZURE_BACKUP_RESOURCE_GROUP=aks_backups_$LOCATION
az group create -n $AZURE_BACKUP_RESOURCE_GROUP --location $LOCATION



#create storage account 
AZURE_STORAGE_ACCOUNT_ID="velero$(uuidgen | cut -d '-' -f5 | tr '[A-Z]' '[a-z]')"

az storage account create \
    --name $AZURE_STORAGE_ACCOUNT_ID \
    --resource-group $AZURE_BACKUP_RESOURCE_GROUP \
    --sku Standard_GRS \
    --encryption-services blob \
    --https-only true \
    --kind BlobStorage \
    --access-tier Hot


#create blob container 

BLOB_CONTAINER=velero

az storage container create -n $BLOB_CONTAINER --public-access off --account-name $AZURE_STORAGE_ACCOUNT_ID


#get the nodes resource group for your cluster the (MC_*) one 
AZURE_RESOURCE_GROUP=$(az aks show -g $RG -n $AKS_CLUSTER_NAME --query nodeResourceGroup -o tsv)


#now we need to create an identity for velero so it can handle backup and restores for volumes, we will use AAD Pod Identity for this 

#enable Pod Identity Preview on the cluster 
az aks update -g $RG -n $AKS_CLUSTER_NAME --enable-pod-identity --enable-pod-identity-with-kubenet


#create a managed identity 
IDENTITY_RESOURCE_GROUP=$RG
IDENTITY_NAME="veleroid-$(uuidgen | cut -d '-' -f5 | tr '[A-Z]' '[a-z]')"
az identity create --resource-group ${IDENTITY_RESOURCE_GROUP} --name ${IDENTITY_NAME}
IDENTITY_CLIENT_ID="$(az identity show -g ${IDENTITY_RESOURCE_GROUP} -n ${IDENTITY_NAME} --query clientId -otsv)"
IDENTITY_RESOURCE_ID="$(az identity show -g ${IDENTITY_RESOURCE_GROUP} -n ${IDENTITY_NAME} --query id -otsv)"

## We need to assign the identity a role, for sake of this demo we will go with contributor, but this can be locked down of course to only the resource group or even tighter 
NODE_GROUP=$(az aks show -g $RG -n $AKS_CLUSTER_NAME --query nodeResourceGroup -o tsv)
NODES_RESOURCE_ID=$(az group show -n $NODE_GROUP -o tsv --query "id")
az role assignment create --role Contributor --assignee $IDENTITY_CLIENT_ID --scope /subscriptions/$AZURE_BACKUP_SUBSCRIPTION_ID 


## now we need to create the POD Identity inside the cluster 
POD_IDENTITY_NAME="velero-podid"
POD_IDENTITY_NAMESPACE="velero" ##this is where we are going to insall veleo as well 
az aks pod-identity add --resource-group $RG --cluster-name $AKS_CLUSTER_NAME --namespace ${POD_IDENTITY_NAMESPACE}  --name ${POD_IDENTITY_NAME} --identity-resource-id ${IDENTITY_RESOURCE_ID}

## validate the identity was created 
kubectl get azureidentity -n velero
NAME                  AGE
velero-podid          2m30s

kubectl get azureidentitybindings -n velero
NAME                          AGE
velero-podid-binding          2m30s





#create a file which contains the environment variables 
cat << EOF  > ./credentials-velero
AZURE_SUBSCRIPTION_ID=${AZURE_BACKUP_SUBSCRIPTION_ID}
AZURE_RESOURCE_GROUP=${AZURE_RESOURCE_GROUP}
AZURE_CLOUD_NAME=AzurePublicCloud
EOF



#install velero client on your local machine, i'm using a Mac, follow this link for to install the appropiate client for your OS of choice https://github.com/vmware-tanzu/velero-plugin-for-microsoft-azure#install-and-start-velero

brew install velero


#install velero in the cluster, this will install velero deployment along with all the required role assignments and a bunch of CRDs

velero install \
    --provider azure \
    --plugins velero/velero-plugin-for-microsoft-azure:v1.2.0 \
    --bucket $BLOB_CONTAINER \
    --secret-file ./credentials-velero \
    --backup-location-config resourceGroup=$AZURE_BACKUP_RESOURCE_GROUP,storageAccount=$AZURE_STORAGE_ACCOUNT_ID,subscriptionId=$AZURE_BACKUP_SUBSCRIPTION_ID \
    --snapshot-location-config apiTimeout=5m,resourceGroup=$AZURE_BACKUP_RESOURCE_GROUP,subscriptionId=$AZURE_BACKUP_SUBSCRIPTION_ID

## check logs 
kubectl logs deployment/velero -n velero

## check the deployment 
kubectl get pods -n velero
NAME                     READY   STATUS    RESTARTS   AGE
velero-fd698b4d9-rvqqj   1/1     Running   0          44s

## now we need to instruct velero to use the Pod Identity we created earlier, we need to edit the deployment to add your identity (add a label for the aadpodidbinding just below the component: velero lable)

kubectl edit deployments.apps -n velero

apiVersion: apps/v1
kind: Deployment
metadata:
  annotations:
    deployment.kubernetes.io/revision: "1"
  creationTimestamp: "2021-07-15T13:19:36Z"
  generation: 1
  labels:
    component: velero
    #here
    aadpodidbinding: velero-podid

## you will need to add the same label to the pod too (this can be avoided if you're using helm to install velero)
kubectl edit pods -n velero velero-fd698b4d9-xj9ks
apiVersion: v1
kind: Pod
metadata:
  annotations:
    prometheus.io/path: /metrics
    prometheus.io/port: "8085"
    prometheus.io/scrape: "true"
  creationTimestamp: "2021-09-21T20:32:09Z"
  generateName: velero-fd698b4d9-
  labels:
    aadpodidbinding: velero-podid
    component: velero
    deploy: velero


#validate what was created 
kubectl get backupstoragelocations.velero.io default -n velero -o yaml

kubectl get volumesnapshotlocations.velero.io -n velero -o yaml

#now that velero is up and running lets test backup and restore 

#as our default namespace only has the mysql deployment, we will backup the whole namespace 
velero backup create mysql-backup-v1 --include-namespaces default

#check your backup (you should see in progress and after few seconds you shuold see completed)
velero backup describe mysql-backup-v1

Name:         mysql-backup-v1
Namespace:    velero
Labels:       velero.io/storage-location=default
Annotations:  velero.io/source-cluster-k8s-gitversion=v1.21.2
              velero.io/source-cluster-k8s-major-version=1
              velero.io/source-cluster-k8s-minor-version=21

Phase:  Completed
....



#check the logs 
velero backup logs mysql-backup-v1

#now delete your statefulset and the pvc, wait until you make sure they got deleted 
kubectl delete -f mysql-statefulset.yaml
kubectl delete pvc data-mysql-0


#restore your backup 
velero restore create  --from-backup mysql-backup-v1 

Restore request "mysql-backup-v1-20210921224325" submitted successfully.
Run `velero restore describe mysql-backup-v1-20210921224325` or `velero restore logs mysql-backup-v1-20210921224325` for more details.

## now lets verify that things are working, this would take couple of minutes 
kubectl get pods -w         

NAME      READY   STATUS    RESTARTS   AGE
mysql-0   2/2     Running   0          74s

## check the data exist 
kubectl run mysql-client --image=mysql:5.7 -i -t --rm --restart=Never --\
  mysql -h mysql-read -e "SELECT * FROM zrstest.messages"


+----------------+
| message        |
+----------------+
| Hello from ZRS |
+----------------+
pod "mysql-client" deleted

#this concludes the demo 

```