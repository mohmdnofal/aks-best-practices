## AKS Cluster Upgrades Using Node Pools

Besides offering different VM SKUs running under the same AKS cluster, node pools can also help with performing Blue/Green type of cluster upgrades as most of the API calls are node pool level now, please check the [node pools docs](https://docs.microsoft.com/en-us/azure/aks/use-multiple-node-pools) to learn more. 

#### The Demo
We will perform a blue/green cluster upgrade using node pools.

```shell
#lets see what versions are available for us in AKS
$ az aks get-versions -l westeurope -o table
KubernetesVersion    Upgrades
-------------------  ----------------------------------------
1.15.4(preview)      None available
1.15.3(preview)      1.15.4(preview)
1.14.7               1.15.3(preview), 1.15.4(preview)
1.14.6               1.14.7, 1.15.3(preview), 1.15.4(preview)
1.13.11              1.14.6, 1.14.7
1.13.10              1.13.11, 1.14.6, 1.14.7
1.12.8               1.13.10, 1.13.11
1.12.7               1.12.8, 1.13.10, 1.13.11
1.11.10              1.12.7, 1.12.8
1.11.9               1.11.10, 1.12.7, 1.12.8
1.10.13              1.11.9, 1.11.10
1.10.12              1.10.13, 1.11.9, 1.11.10
```

1. Create an AKS cluster
```shell
#Lets spin up a cluster using K8s v1.13.11 with a single node pool called nodepool1311
#define the variables
location=westeurope
rg=ignite
clustername=aks-nodepools-upgrade
vmsize=Standard_B2s
k8s_version="1.13.11"
node_count=1

#create  the  resource group 
$ az group create --name $rg --location $location
#create the cluster
$ az aks create \
    --resource-group $rg \
    --name $clustername \
    --kubernetes-version $k8s_version \
    --generate-ssh-keys \
    --enable-vmss \
    --load-balancer-sku standard \
    --node-count 1 \
    --nodepool-name node1311 \
    --location $location

#get the cluster credentials 
$ az aks get-credentials --resource-group $rg --name $clustername

#check if things are in order
$ kubectl get nodes
NAME                               STATUS   ROLES   AGE   VERSION
aks-node1311-64268756-vmss000000   Ready    agent   14m   v1.13.11
```

2. Deploy your application 

```shell
#deploy the application and expose it using type loadbalancer
$ kubectl apply  -f myapp-v1.yaml
$ kubectl apply -f myapp-service.yaml

#check that the app is running
$ kubectl get pods -l app=myapp-v1

#check if you got an external IP for your app
kubectl get svc myapp
NAME    TYPE           CLUSTER-IP    EXTERNAL-IP      PORT(S)        AGE
myapp   LoadBalancer   10.0.186.61   51.145.184.112   80:31827/TCP   2m25s

#check if your app is running, the below command only output  the HTTP status code
$ curl -I 51.145.184.112 2>/dev/null | head -n 1 | cut -d$' ' -f2
200

#check the endpoints 
kubectl get endpoints myapp
NAME    ENDPOINTS                                                 AGE
myapp   10.244.0.10:80,10.244.0.11:80,10.244.0.8:80 + 1 more...   11m
```



3. Now, there is a new k8s version available in AKS "1.14.8" and we are interested in upgrading

```shell
az aks get-upgrades -n $clustername -g $rg
{
  "agentPoolProfiles": null,
  "controlPlaneProfile": {
    "kubernetesVersion": "1.13.11",
    "name": null,
    "osType": "Linux",
    "upgrades": [
      {
        "isPreview": null,
        "kubernetesVersion": "1.14.7"
      },
      {
        "isPreview": null,
        "kubernetesVersion": "1.14.8"
      },
      {
        "isPreview": null,
        "kubernetesVersion": "1.13.12"
      }
    ]
  },
  "id": "/subscriptions/2db66428-abf9-440c-852f-641430aa8173/resourcegroups/ignite/providers/Microsoft.ContainerService/managedClusters/aks-nodepools-upgrade/upgradeprofiles/default",
  "name": "default",
  "resourceGroup": "ignite",
  "type": "Microsoft.ContainerService/managedClusters/upgradeprofiles"
}
```

4. With nodepools available in AKS, we have the ability to decouple the Control Plane upgrade from the nodes upgrade, and we will start by upgrading our control plane. 

**Note** Before we start, at this stage you should:
1- Be fully capable of spinning up your cluster and restore your data in case of any failure (check the backup and restore section)
2- Know that control plane upgrades don't impact the application as its running on the nodes
3- You know that your risk is a failure on the Control Plane and in case this happened you should go and spin up a new cluster and migrate then open a support case to understand what went wrong.


```shell
$ az aks upgrade -n $clustername -g $rg -k 1.14.8 --control-plane-only
Kubernetes may be unavailable during cluster upgrades.
Are you sure you want to perform this operation? (y/n): y
Since control-plane-only argument is specified, this will upgrade only the control plane to 1.14.8. Node pool will not change. Continue? (y/N): y
{
  "aadProfile": null,
  "addonProfiles": null,
  "agentPoolProfiles": [
    {
      "availabilityZones": null,
      "count": 1,
      "enableAutoScaling": null,
      "enableNodePublicIp": null,
      "maxCount": null,
      "maxPods": 110,
      "minCount": null,
      "name": "node1311",
      "nodeTaints": null,
      "orchestratorVersion": "1.13.11",
      "osDiskSizeGb": 100,
      "osType": "Linux",
      "provisioningState": "Succeeded",
      "scaleSetEvictionPolicy": null,
      "scaleSetPriority": null,
      "type": "VirtualMachineScaleSets",
      "vmSize": "Standard_DS2_v2",
      "vnetSubnetId": null
    }
  ],
  "apiServerAccessProfile": null,
  "dnsPrefix": "aks-nodepo-ignite-2db664",
  "enablePodSecurityPolicy": false,
  "enableRbac": true,
  "fqdn": "aks-nodepo-ignite-2db664-6e9c6763.hcp.westeurope.azmk8s.io",
  "id": "/subscriptions/2db66428-abf9-440c-852f-641430aa8173/resourcegroups/ignite/providers/Microsoft.ContainerService/managedClusters/aks-nodepools-upgrade",
  "identity": null,
  "kubernetesVersion": "1.14.8",
 ....
```

**Note** The Control Plane can support N-2 kubelet on the nodes, which means 1.14 Control Plane supports 1.14,1.12, and 1.11 Kubelet. Kubelet can't be *newer* than the Control Plane. more information can be found [here](https://kubernetes.io/docs/setup/release/version-skew-policy/#kube-apiserver)


5. Lets add a new node pool with the desired version "1.14.8"

```shell
#Warring confusing parameters :) 
$ az aks nodepool add \
    --cluster-name $clustername \
    --resource-group $rg \
    --name node1418 \
    --node-count $node_count \
    --node-vm-size $vmsize \
    --kubernetes-version 1.14.8

#Lets see how our nodes look like (we should 2 see 2 nodes with different K8s versions)
$ kubectl get nodes 
NAME                               STATUS   ROLES   AGE   VERSION
aks-node1311-64268756-vmss000000   Ready    agent   40m   v1.13.11
aks-node1418-64268756-vmss000000   Ready    agent   75s   v1.14.8
```


7. TEST TEST TEST, in whatever way you need to test to verify that your application will run on the new node pool, normally you will spin up a test version of your application, if things are in order then proceed to 8.

8. Deploy your application, different options are available 

* Migrate off the old nodes using cordon and drain 

```shell
#deploy a new version of your application on the new nodes, you can target the new node  pool using the "agentpool=" label which was added from AKS
$ kubectl get nodes --show-labels
NAME                               STATUS   ROLES   AGE   VERSION    LABELS
aks-node1311-64268756-vmss000000   Ready    agent   57m   v1.13.11   agentpool=node1311,...
aks-node1418-64268756-vmss000000   Ready    agent   17m   v1.14.8    agentpool=node1418,...

#open another shell and run the below script to see the impact of the upgrade process
$ while true;do curl -I 51.145.184.112 2>/dev/null | head -n 1 | cut -d$' ' -f2;  done
200
200
....

#deploy the new app, we will change the name only and keep the labels and add node affinity
$ kubectl apply -f myapp-v2.yaml

#check if the pods are running, note that all the new pods are in the new node
$ kubectl get pods -o wide
NAME                        READY   STATUS    RESTARTS   AGE   IP            NODE                               NOMINATED NODE   READINESS GATES
myapp-v1-7bc994fccc-4wg8c   1/1     Running   0          51m   10.244.0.11   aks-node1311-64268756-vmss000000   <none>           <none>
myapp-v1-7bc994fccc-6q65q   1/1     Running   0          51m   10.244.0.10   aks-node1311-64268756-vmss000000   <none>           <none>
myapp-v1-7bc994fccc-g5jjz   1/1     Running   0          51m   10.244.0.8    aks-node1311-64268756-vmss000000   <none>           <none>
myapp-v1-7bc994fccc-zpdw6   1/1     Running   0          51m   10.244.0.9    aks-node1311-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-bdtpk    1/1     Running   0          25s   10.244.1.4    aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-dc6bc    1/1     Running   0          25s   10.244.1.3    aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-kg56v    1/1     Running   0          25s   10.244.1.2    aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-pwfx2    1/1     Running   0          25s   10.244.1.5    aks-node1418-64268756-vmss000000   <none>           <none> 

#check the endpoints, note now we have 8 instead of 4
kubectl get endpoints myapp
NAME    ENDPOINTS                                                 AGE
myapp   10.244.0.10:80,10.244.0.11:80,10.244.0.8:80 + 5 more...   18m

#delete the old version of your application
$ kubectl delete -f myapp-v1.yaml

#check the pods, you should only see the v2.
$ kubectl get pods -o wide
NAME                       READY   STATUS    RESTARTS   AGE    IP           NODE                               NOMINATED NODE   READINESS GATES
myapp-v2-9c8b897c7-bdtpk   1/1     Running   0          4m1s   10.244.1.4   aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-dc6bc   1/1     Running   0          4m1s   10.244.1.3   aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-kg56v   1/1     Running   0          4m1s   10.244.1.2   aks-node1418-64268756-vmss000000   <none>           <none>
myapp-v2-9c8b897c7-pwfx2   1/1     Running   0          4m1s   10.244.1.5   aks-node1418-64268756-vmss000000   <none>           <none>

#you're good to cordon and drain the old node pool 
$ kubectl delete -f myapp-v1.yaml
deployment.apps "myapp-v1" deleted

$  kubectl drain aks-node1311-64268756-vmss000000 --ignore-daemonsets  --delete-local-data

#You should see only 200s responses from the curl script running, now you  can exit the script
```

* Deploy your application with a new service, then switch the endpoints in your DNS
* you may not care about a slight down time, then you just cordon and drain the nodes

9. Finish!