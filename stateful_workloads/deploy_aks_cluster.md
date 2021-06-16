# Cluster Creation

## Cluster Setup
Below is how the cluster will look like: 
1. The cluster will have uptime SLA enabled, to ensure master components are spread across availability zones (AZs)
2. System Node Pool: system node pool has no state in it, as such we will create a single pool with 3 nodes spread across 3 availability zones 
3. User Node Pools: this is where our application will be hosted, we will create 3 node pools with 2 nodes each which will be spread across 3 AZs 
4. Taint user node pools to ensure nothing else land in the pool but our application
5. Auto Scaling will be enabled in each node pool
6. Networking model: Kubenet or CNI don't make a difference here, we will use CNI to ensure max network performance for pods 
7. We will be using ephemeral disks for the nodes operating system 
8. We will be using managed identities 
9. Enable monitoring on the cluster
10. For sake of simplicity we won't be integrating with Azure AD

Here is how the cluster will look like 
![ES AKS Cluster](es-aks-cluster.png)


## Cluster Deployment

```shell
##configure cluster parameters
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
K8S_VERSION=$(az aks get-versions  -l $LOCATION --query 'orchestrators[-2].orchestratorVersion' -o tsv) #get latest GA k8s version 
SYSTEM_POOL_NAME=systempool
STORAGE_POOL_ZONE1_NAME=espoolz1
STORAGE_POOL_ZONE2_NAME=espoolz2
STORAGE_POOL_ZONE3_NAME=espoolz3
IDENTITY_NAME=$AKS_NAME`date +"%d%m%y"` # cluster managed identity


##Create resource group
$ az group create --name $RG --location $LOCATION


##create the cluster identity
$ az identity create --name $IDENTITY_NAME --resource-group $RG

##get the identity id and clientid, we will use them later 
$ IDENTITY_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query id -o tsv)
$ IDENTITY_CLIENT_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RG --query clientId -o tsv)


##Create the VNET and Subnet 
$ az network vnet create \
  --name $AKS_VNET_NAME \
  --resource-group $RG \
  --location $LOCATION \
  --address-prefix $AKS_VNET_CIDR \
  --subnet-name $AKS_NODES_SUBNET_NAME \
  --subnet-prefix $AKS_NODES_SUBNET_PREFIX

##get the RG and VNET IDs
$ RG_ID=$(az group show -n $RG  --query id -o tsv)
$ VNETID=$(az network vnet show -g $RG --name $AKS_VNET_NAME --query id -o tsv)


##Assign the managed identity permissions on the RG and VNET
$ az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $RG_ID --role Contributor
$ az role assignment create --assignee $IDENTITY_CLIENT_ID --scope $VNETID --role Contributor

##Validate Role Assignment
$ az role assignment list --assignee $IDENTITY_CLIENT_ID --all -o table

Principal                             Role         Scope
------------------------------------  -----------  -------------------------------------------------------------------------------------------------------------------------------------------------------
c068a2aa-02b2-40b1-ba2c-XXXXXXXXXXXX  Contributor  /subscriptions/SUBID/resourceGroups/aks-storage-westus2
c068a2aa-02b2-40b1-ba2c-XXXXXXXXXXXX  Contributor  /subscriptions/SUBID/resourceGroups/aks-storage-westus2/providers/Microsoft.Network/virtualNetworks/aks-storage-vnet

#get the subnet id 
$ AKS_VNET_SUBNET_ID=$(az network vnet subnet show --name $AKS_NODES_SUBNET_NAME -g $RG --vnet-name $AKS_VNET_NAME --query "id" -o tsv)


### create the cluster 
$ az aks create \
-g $RG \
-n $AKS_CLUSTER_NAME \
-l $LOCATION \
--node-count $SYSTEM_NODE_COUNT \
--node-vm-size $NODES_SKU \
--network-plugin $NETWORK_PLUGIN \
--network-policy $NETWORK_POLICY \
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
--zones 1 2 3 \
--node-osdisk-type Ephemeral \
--node-osdisk-size 100




### get the credentials 
$ az aks get-credentials -n $AKS_CLUSTER_NAME -g $RG

##validate nodes are running and spread across AZs
$ kubectl get nodes

aks-systempool-41985791-vmss000000   Ready    agent   21h   v1.20.7
aks-systempool-41985791-vmss000001   Ready    agent   21h   v1.20.7
aks-systempool-41985791-vmss000002   Ready    agent   21h   v1.20.7

##check the system nodes spread over availaiblity zones 
$ kubectl describe nodes -l agentpool=systempool | grep -i topology.kubernetes.io/zone
                    
                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-3


##now we need to add our node pools 

##First Node Pool in Zone 1
$ az aks nodepool add \
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
--node-osdisk-type Ephemeral \
--node-osdisk-size 100 \
--no-wait

##Second Node Pool in Zone 2
$ az aks nodepool add \
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
--node-osdisk-type Ephemeral \
--node-osdisk-size 100 \
--no-wait


##Third Node Pool in Zone 3
$ az aks nodepool add \
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
--node-osdisk-type Ephemeral \
--node-osdisk-size 100 \
--no-wait


##it will take couple of minutes to add the nodes, validate that nodes are added to the cluster and spread correctly 
$ kubectl get nodes -l dept=dev                                      

NAME                               STATUS   ROLES   AGE   VERSION
aks-espoolz1-41985791-vmss000000   Ready    agent   21h   v1.20.7
aks-espoolz1-41985791-vmss000001   Ready    agent   21h   v1.20.7
aks-espoolz2-41985791-vmss000000   Ready    agent   21h   v1.20.7
aks-espoolz2-41985791-vmss000001   Ready    agent   21h   v1.20.7
aks-espoolz3-41985791-vmss000000   Ready    agent   21h   v1.20.7
aks-espoolz3-41985791-vmss000001   Ready    agent   21h   v1.20.7


$ kubectl describe nodes -l dept=dev | grep -i topology.kubernetes.io/zone
  
                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-1
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-2
                    topology.kubernetes.io/zone=westus2-3
                    topology.kubernetes.io/zone=westus2-3

##the Nodepool name will be added to the "agentpool" label on the nodes 
$ kubectl describe nodes -l dept=dev | grep -i agentpool

Labels:             agentpool=espoolz1
Labels:             agentpool=espoolz1
Labels:             agentpool=espoolz2
Labels:             agentpool=espoolz2
Labels:             agentpool=espoolz3
Labels:             agentpool=espoolz3

```

Continue to next section [Deploy Elastic Search Cluster](deploy_elasticsearch.md)


