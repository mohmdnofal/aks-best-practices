## AKS With Availability Zones

AKS Now supports [Availability Zones (AZs)](https://docs.microsoft.com/en-us/azure/availability-zones/az-overview) the official AKS docs can be found [here](https://docs.microsoft.com/en-us/azure/aks/availability-zones) .

With AZs AKS can offer higher availability for your applications as they will spread across different AZs to achieve an SLA of 99,99%.

AKS with AZs support requires the use of [Standard Load Balancer (SLB)](https://docs.microsoft.com/en-us/azure/aks/load-balancer-standard), also note that disks are AZ bound by default.

#### Demo#1 Create an AKS cluster which spans AZs

1. Create an AKS Cluster
```shell
#define your variables
location=westeurope
rg=ignite
clustername=aks-ignite-azs
vmsize=Standard_B2s
k8s_version="1.14.7"

#create the cluster
$ az aks create \
    --resource-group $rg \
    --name $clustername \
    --kubernetes-version $k8s_version \
    --generate-ssh-keys \
    --enable-vmss \
    --load-balancer-sku standard \
    --node-count 3 \
    --node-zones 1 2 3 \
    --location $location

#get the credintials 
$ az aks get-credentials --resource-group $rg --name $clustername
```

2. Verify the nodes are spread across AZs (you can remove the '-l agentpool=nodes1')

```shell
$ kubectl describe nodes -l agentpool=nodes1 | grep -e "Name:" -e "failure-domain.beta.kubernetes.io/zone"
Name:               aks-nodes1-14441868-vmss000000
                    failure-domain.beta.kubernetes.io/zone=westeurope-1
Name:               aks-nodes1-14441868-vmss000001
                    failure-domain.beta.kubernetes.io/zone=westeurope-2
Name:               aks-nodes1-14441868-vmss000002
                    failure-domain.beta.kubernetes.io/zone=westeurope-3

$ kubectl get nodes -l agentpool=nodes1 --show-labels
NAME                             STATUS   ROLES   AGE   VERSION   LABELS
aks-nodes1-14441868-vmss000000   Ready    agent   44d   v1.14.7   agentpool=nodes1,beta.kubernetes.io/arch=amd64,beta.kubernetes.io/instance-type=Standard_B2s,beta.kubernetes.io/os=linux,failure-domain.beta.kubernetes.io/region=westeurope,**failure-domain.beta.kubernetes.io/zone=westeurope-1**,...
aks-nodes1-14441868-vmss000001   Ready    agent   44d   v1.14.7   agentpool=nodes1,beta.kubernetes.io/arch=amd64,beta.kubernetes.io/instance-type=Standard_B2s,beta.kubernetes.io/os=linux,failure-domain.beta.kubernetes.io/region=westeurope,failure-domain.beta.kubernetes.io/zone=westeurope-2,...
aks-nodes1-14441868-vmss000002   Ready    agent   44d   v1.14.7   agentpool=nodes1,beta.kubernetes.io/arch=amd64,beta.kubernetes.io/instance-type=Standard_B2s,beta.kubernetes.io/os=linux,failure-domain.beta.kubernetes.io/region=westeurope,failure-domain.beta.kubernetes.io/zone=westeurope-3,...
```

Now you maybe wondering where did this label "failure-domain.beta.kubernetes.io/zone" come from, this label is automatically assigned by the cloud provider and its very important for how will you create affinity rules for your workloads deployed in Kubernetes, to learn more please check [here](https://kubernetes.io/docs/reference/kubernetes-api/labels-annotations-taints/#failure-domain-beta-kubernetes-io-zone) .

The Kube Scheduler will automatically understand that the spreading behavior should be extended across zones, and it will try in "best effort" to distribute your pods evenly across zones assuming your nodes are heterogeneous (similar SKU), to learn more about how the Kube Scheduler works check [here](https://kubernetes.io/docs/concepts/scheduling/kube-scheduler/) .


#### Demo#2 Deploy an application across AZs

Deploy a demo app using the Nginx image 
```shell
$ kubectl run az-test --image=nginx --replicas=6
deployment.apps/az-test created
# verify the spread behavior 
kubectl get pods -l run=az-test -o wide 
NAME                       READY   STATUS    RESTARTS   AGE   IP            NODE                             NOMINATED NODE   READINESS GATES
az-test-5b6b9977dd-2d4pp   1/1     Running   0          8s    10.244.0.24   aks-nodes1-14441868-vmss000002   <none>           <none>
az-test-5b6b9977dd-5lllz   1/1     Running   0          8s    10.244.0.35   aks-nodes1-14441868-vmss000002   <none>           <none>
az-test-5b6b9977dd-jg67d   1/1     Running   0          8s    10.244.1.36   aks-nodes1-14441868-vmss000000   <none>           <none>
az-test-5b6b9977dd-nks9k   1/1     Running   0          8s    10.244.2.31   aks-nodes1-14441868-vmss000001   <none>           <none>
az-test-5b6b9977dd-xgj5f   1/1     Running   0          8s    10.244.1.37   aks-nodes1-14441868-vmss000000   <none>           <none>
az-test-5b6b9977dd-xqrwl   1/1     Running   0          8s    10.244.2.30   aks-nodes1-14441868-vmss000001   <none>           <none>
```

you can see from the above that because my nodes are heterogeneous and mostly  have the same usage, the Kube Scheduler managed to achieve even spread across the AZs


#### Demo#3 Deploy to specific AZs by using Affinity 

The example here is a 2 tier application (Frontend and Backend), Backend needs to be deployed in AZs 1 and 2 only, and because my Frontends require super low latency I want the scheduler to allocate my pods next to my Backend pods.

For the Backend we will be using [Node Affinity](https://kubernetes.io/docs/concepts/configuration/assign-pod-node/#node-affinity) rules and for the Frontend we will be using [Inter-Pod Affinity](https://kubernetes.io/docs/concepts/configuration/assign-pod-node/#node-affinity) rules.

To achieve the above i'll be adding the below to my Backend deployment file, i'm essentially asking for my pods to be scheduled in Zone 1 and 2 in West Europe.
```yaml
affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: failure-domain.beta.kubernetes.io/zone
                operator: In
                values:
                - westeurope-1
                - westeurope-2
```

And the below to my Frontend deployment file, here i'm asking that my pod should land in a zoned node where there is at least one pod that holds the "app=backend" label
```yaml
     affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - backend
            topologyKey: failure-domain.beta.kubernetes.io/zone
```

Moving to our actual demo, deploy your apps 
```shell
$ kubectl apply -f backend.yaml
deployment.apps/backend-deployment created
#wait until all the pods are running
$ kubectl get pods -l app=backend -w (ctrl+C when you are done)
NAME                                  READY   STATUS    RESTARTS   AGE
backend-deployment-5cc466474d-6z72s   1/1     Running   0          11s
backend-deployment-5cc466474d-f26s8   1/1     Running   0          12s
backend-deployment-5cc466474d-wmhpv   1/1     Running   0          11s
backend-deployment-5cc466474d-zrhr4   1/1     Running   0          11s

#deploy your frontend
$ kubectl apply -f frontend.yaml
deployment.apps/frontend-deployment created
$ kubectl get pods -l app=frontend -w
```

lets verify the placement of the pods 
```shell
$ kubectl get pods -l app=backend -o wide 
NAME                                  READY   STATUS    RESTARTS   AGE   IP            NODE                             NOMINATED NODE   READINESS GATES
backend-deployment-5cc466474d-6z72s   1/1     Running   0          97s   10.244.2.32   aks-nodes1-14441868-vmss000001   <none>           <none>
backend-deployment-5cc466474d-f26s8   1/1     Running   0          98s   10.244.2.33   aks-nodes1-14441868-vmss000001   <none>           <none>
backend-deployment-5cc466474d-wmhpv   1/1     Running   0          97s   10.244.1.39   aks-nodes1-14441868-vmss000000   <none>           <none>
backend-deployment-5cc466474d-zrhr4   1/1     Running   0          97s   10.244.1.38   aks-nodes1-14441868-vmss000000   <none>           <none>
$ kubectl get pods -l app=frontend -o wide
NAME                                   READY   STATUS    RESTARTS   AGE   IP            NODE                             NOMINATED NODE   READINESS GATES
frontend-deployment-7665467f6b-5k8xz   1/1     Running   0          46s   10.244.2.35   aks-nodes1-14441868-vmss000001   <none>           <none>
frontend-deployment-7665467f6b-g78xd   1/1     Running   0          46s   10.244.1.40   aks-nodes1-14441868-vmss000000   <none>           <none>
frontend-deployment-7665467f6b-mbndr   1/1     Running   0          46s   10.244.2.34   aks-nodes1-14441868-vmss000001   <none>           <none>
frontend-deployment-7665467f6b-n4vnm   1/1     Running   0          46s   10.244.1.41   aks-nodes1-14441868-vmss000000   <none>           <none>
```

You can see from the above how you can influence the scheduler to achieve your business needs, and how beautiful AZs are:) 


#### Note
Cross AZ traffic is [charged](https://azure.microsoft.com/en-us/pricing/details/bandwidth/) if you have very chatty services you may want to allocate them in one Zone, with the option of failing over on others in case of failure.

