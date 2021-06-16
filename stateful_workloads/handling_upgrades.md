# Introduction 
Handling cluster upgrades when you have statefulsets requires more attention, as there is data involved and we need to ensure availability and no data corruption throughout the process. 

Then again, if you have the right architecture for your cluster and applications, it makes things easier, as we can tolerate the failure of a full zone while our application isn't impacted, this makes planning the upgrades a smoother process




## How can we handle upgrades for stateful applications

I assume that you're familiar with the [AKS Upgrade Options](https://docs.microsoft.com/en-us/azure/aks/upgrade-cluster), if note, please do.

To assume full control over the upgrade process, its never advisable just to upgrade the whole cluster at once, we need to go on a per zone basis, this would give us some room to make the upgrade process smoother and easier. 

1. **Option#1 NodePool Blue/Green Upgrade** 
To ensure a safe upgrade operation, we recommend a blue/green approach either with new node pools or new cluster, this is how we are going to do it on per node pool basis
- Upgrade the control plane
##On a new terminal run the below script again to check the application status while we are performing the upgrade, there should be no downtime
```shell
 while true
do
curl -s -o /dev/null -w "%{http_code}" http://$esip:9200/test/_search\?q\=user:mo\*
echo \\n
done

#you should see something like the below "hopefully"!
200

200

200

200
```

##check what new versions are available to you
```shell
az aks upgrade -n $AKS_CLUSTER_NAME -g $RG --control-plane-only --kubernetes-version

Name     ResourceGroup        MasterVersion    Upgrades
-------  -------------------  ---------------  ---------------
default  aks-storage-westus2  1.20.7           1.21.1(preview)
```

##We can see that we have 1.21.1 as a possible version, so lets open a terminal on the side and run the control plane upgrade command
```shell
$ az aks upgrade \
-n $AKS_CLUSTER_NAME \
-g $RG \
--control-plane-only \
--kubernetes-version 1.21.1 \
--yes 
```

##Below video is an illustration for the process (feel free to play at max possible speed)
[place holder]
- Create a new node pool with the new version (same labels, same taints)

#lets add a new node pool called (espoolz1v2) to the first zone with new k8s version 1.21.1
```shell
$ az aks nodepool add \
--cluster-name $AKS_CLUSTER_NAME \
--mode User \
--name espoolz1v2 \
--kubernetes-version 1.21.1 \
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
```

#validate the setup (we should see a new node pool with 2 nodes running v1.21.1)
```shell
$ kubectl get nodes

NAME                                 STATUS   ROLES   AGE   VERSION
aks-espoolz1-41985791-vmss000000     Ready    agent   46h   v1.20.7
aks-espoolz1-41985791-vmss000001     Ready    agent   46h   v1.20.7
aks-espoolz1v2-41985791-vmss000000   Ready    agent   89s   v1.21.1
aks-espoolz1v2-41985791-vmss000001   Ready    agent   86s   v1.21.1
aks-espoolz2-41985791-vmss000000     Ready    agent   46h   v1.20.7
aks-espoolz2-41985791-vmss000001     Ready    agent   46h   v1.20.7
aks-espoolz3-41985791-vmss000000     Ready    agent   46h   v1.20.7
aks-espoolz3-41985791-vmss000001     Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000000   Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000001   Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000002   Ready    agent   46h   v1.20.7
```

- on another terminal run the script to check the availability of the application
```shell 
while true
do
curl -s -o /dev/null -w "%{http_code}" http://$esip:9200/test/_search\?q\=user:mo\*
echo \\n
done

#you should see something like the below "hopefully"!
200

200

200

200
```

- Upgrade your helm file by adding the new node pool in the affinity rules, we will replace "espoolz1" with "espoolz1v2", the file values_nodepool_upgrade.yaml has the update values, but below for reference
```yaml
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: agentpool
                  operator: In
                  values:
                  - espoolz1v2 ##our new node pool
                  - espoolz2
                  - espoolz3
```

- Upgrade the application 
```shell 
helm upgrade -f values_nodepool_upgrade.yaml elasticsearch-v1 bitnami/elasticsearch -n elasticsearch
``` 

#check the status of your pods, you should see pods getting terminated and moving the new node pool, below is the final status 
```shell
kubectl get pods  -n elasticsearch -o wide   
NAME                                                  READY   STATUS    RESTARTS   AGE     IP             NODE                                 NOMINATED NODE   READINESS GATES
elasticsearch-v1-coordinating-only-567bfb67db-8xgkc   1/1     Running   0          3m54s   172.16.0.185   aks-espoolz3-41985791-vmss000000     <none>           <none>
elasticsearch-v1-coordinating-only-567bfb67db-b49lg   1/1     Running   0          3m52s   172.16.0.211   aks-espoolz3-41985791-vmss000001     <none>           <none>
elasticsearch-v1-coordinating-only-567bfb67db-gjxdx   1/1     Running   0          3m52s   172.16.0.222   aks-espoolz2-41985791-vmss000000     <none>           <none>
elasticsearch-v1-coordinating-only-567bfb67db-n54z4   1/1     Running   0          3m49s   172.16.1.75    aks-espoolz1v2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-coordinating-only-567bfb67db-rgf99   1/1     Running   0          3m54s   172.16.1.30    aks-espoolz1v2-41985791-vmss000000   <none>           <none>
elasticsearch-v1-coordinating-only-567bfb67db-zhlhw   1/1     Running   0          3m54s   172.16.1.14    aks-espoolz2-41985791-vmss000001     <none>           <none>
elasticsearch-v1-data-0                               1/1     Running   0          74s     172.16.0.160   aks-espoolz3-41985791-vmss000000     <none>           <none>
elasticsearch-v1-data-1                               1/1     Running   0          94s     172.16.1.0     aks-espoolz2-41985791-vmss000001     <none>           <none>
elasticsearch-v1-data-2                               1/1     Running   0          2m10s   172.16.1.79    aks-espoolz1v2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-3                               1/1     Running   0          2m54s   172.16.0.197   aks-espoolz3-41985791-vmss000001     <none>           <none>
elasticsearch-v1-data-4                               1/1     Running   0          3m40s   172.16.1.40    aks-espoolz1v2-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-5                               1/1     Running   0          3m52s   172.16.0.234   aks-espoolz2-41985791-vmss000000     <none>           <none>
elasticsearch-v1-master-0                             1/1     Running   0          2m48s   172.16.1.81    aks-espoolz1v2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-master-1                             1/1     Running   0          3m34s   172.16.0.204   aks-espoolz3-41985791-vmss000001     <none>           <none>
elasticsearch-v1-master-2                             1/1     Running   0          3m46s   172.16.0.229   aks-espoolz2-41985791-vmss000000     <none>           <none>
```

- now you can delete the first node pool 

##delete the first node pool 
```shell 
$ az aks nodepool delete \
--cluster-name $AKS_CLUSTER_NAME \
--name espoolz1 \
-g $RG
```
##this what you should end up with 
```shell
$ kubectl get nodes
NAME                                 STATUS   ROLES   AGE   VERSION
aks-espoolz1v2-41985791-vmss000000   Ready    agent   16m   v1.21.1
aks-espoolz1v2-41985791-vmss000001   Ready    agent   16m   v1.21.1
aks-espoolz2-41985791-vmss000000     Ready    agent   46h   v1.20.7
aks-espoolz2-41985791-vmss000001     Ready    agent   46h   v1.20.7
aks-espoolz3-41985791-vmss000000     Ready    agent   46h   v1.20.7
aks-espoolz3-41985791-vmss000001     Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000000   Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000001   Ready    agent   46h   v1.20.7
aks-systempool-41985791-vmss000002   Ready    agent   46h   v1.20.7
```

- Repeat for the rest of the node pools


2. **Option#2 In-place upgrade** 
The process will be carried in the below steps 
- We upgrade the control plane first, which shouldn't be a breaking process for the application 
##On a new terminal run the below script again to check the application status while we are performing the upgrade, there should be no downtime
```shell
 while true
do
curl -s -o /dev/null -w "%{http_code}" http://$esip:9200/test/_search\?q\=user:mo\*
echo \\n
done

#you should see something like the below "hopefully"!
200

200

200

200
```

##check what new versions are available to you
```shell
az aks upgrade -n $AKS_CLUSTER_NAME -g $RG --control-plane-only --kubernetes-version

Name     ResourceGroup        MasterVersion    Upgrades
-------  -------------------  ---------------  ---------------
default  aks-storage-westus2  1.20.7           1.21.1(preview)
```

##We can see that we have 1.21.1 as a possible version, so lets open a terminal on the side and run the control plane upgrade command
```shell
$ az aks upgrade \
-n $AKS_CLUSTER_NAME \
-g $RG \
--control-plane-only \
--kubernetes-version 1.21.1 \
--yes 
```

##Below video is an illustration for the process (feel free to play at max possible speed)
[place holder]

- We upgrade the node pools, we will go on a per node-pool basis, we finish one and then move to the next
```shell
az aks nodepool update \
--cluster-name $AKS_CLUSTER_NAME \
--name espoolz2 \
--kubernetes-version 1.21.1 \
--resource-group $RG 
``` 

- repeat the validation from Option#1 
- repeate for the rest of the nodepools 


## Summary 
Having a resilient design allows us flexibility on how we handle operations such as upgrade, for a safe upgrade process we recommend having a blue/green approach