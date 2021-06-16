# Deploy Elastic Search Cluster

## Elastic Search Cluster Setup
Its time to deploy our ElasticSearch Cluster to the Azure Kubernetes Service Cluster we just created. ElasticSearch has 3 main components that make up the cluster Client/Coordinating, Masters, and Data Nodes. you can read more about what each one does in elastic [public docs](https://www.elastic.co/guide/index.html).

1. **Client/Coordinating Nodes** Act as a reverse proxy for the clusters, this is what the external world interacts with. its deployed as a k8s deployment with horizontal pod autoscaling enabled, we will try to have a client in each node to minimize data movement across nodes, we can minimize but we can't prevent it from happening. 
2. **Master Nodes** stores the metadata about the data nodes, it will be deployment as a k8s deployment, ideally we need 3. 
3. **Data Nodes** this is where the magic is, this is where the indices are stored and replicated. this would be our Statefulset with persistent volume to persist the data.

Here is how the cluster will look like
![ES Cluster](es-cluster.png)


## Elastic Search Cluster Installation 

### Prepare The Cluster 
1. We need to create our storage class, here is how our storage class will look like.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: es-storageclass #storage class name
parameters:
  kind: Managed #we will use Azure managed disks
  storageaccounttype: Premium_LRS #use premium managed disk
  tags: costcenter=dev,app=elasticsearch  #add tags so all disks related to our application are tagged
provisioner: kubernetes.io/azure-disk
reclaimPolicy: Retain #changed from default "Delete" to "Retain" so we can retain the disks even if the claim is deleted
volumeBindingMode: WaitForFirstConsumer #instrcuts the scheduler to wait for the pod to be scheduled before binding the dikss
```

#create the storage class
```shell
$ kubectl apply -f es-storageclass.yaml
```

2. We will use helm to install the ElasticSearch cluster, we will rely on the ElasticSearch chart provided by bitnami as its the easiest one to navigate. 

#add the bitnami repository
```shell
$ helm repo add bitnami https://charts.bitnami.com/bitnami
```
#show the values file and store it in "values.yaml" file **Note** if you have cloned the repo, you will override the existing file, so maybe change the name :)
```shell
$ helm show values bitnami/elasticsearch > values.yaml
```

### Customize the values.yaml file so it fits our cluster setup

1. Modify the storage class in the global parameters so all disks are created from the storage class we already created 

```yaml
global:
  # imageRegistry: myRegistryName
  # imagePullSecrets:
  #   - myRegistryKeySecretName
  storageClass: es-storageclass
  ## Coordinating name to be used in the Kibana subchart (service name)
  ##
  coordinating:
    name: coordinating-only
  kibanaEnabled: false
```

2. Master Nodes 

#change number of replicas to 3
```yaml
master:
  name: master
  ## Number of master-eligible node(s) replicas to deploy
  ##
  replicas: 3
```

#change the affinity rules, here we are adding 2 rules, the first one will instruct the scheduler to spread across 3 AZs and the second one it will give the preference for our nodepools
```yaml
  affinity: 
          nodeAffinity:
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: topology.kubernetes.io/zone
                  operator: In
                  values:
                  - westus2-1
                  - westus2-2
                  - westus2-3
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: agentpool
                  operator: In
                  values:
                  - espoolz1
                  - espoolz2
                  - espoolz3
```

#modify the tolerations, as you might remember we tainted the nodes while we are creating the node pools so we protect them from other workloads 
```yaml
  tolerations:
            - key: "app"
              operator: "Equal"
              value: "elasticsearch"
              effect: "NoSchedule"
```

#last thing to be done on the masters is to modify the autoscaling parameters 
```yaml
  autoscaling:
    enabled: false
    minReplicas: 3
    maxReplicas: 5
```

3. Client/Coordinating Nodes

#modify the number of replicas, we have 6 nodes so we will have 6 replicas
```yaml
coordinating:
  ## Number of coordinating-only node(s) replicas to deploy
  ##
  replicas: 6
```

#we will do the exact same as in the masters for the affinity and tolerations 
```yaml
  affinity: 
          nodeAffinity:
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: topology.kubernetes.io/zone
                  operator: In
                  values:
                  - westus2-1
                  - westus2-2
                  - westus2-3
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: agentpool
                  operator: In
                  values:
                  - espoolz1
                  - espoolz2
                  - espoolz3

  ## Node labels for pod assignment
  ## Ref: https://kubernetes.io/docs/user-guide/node-selection/
  ##
  nodeSelector: {}

  ## Tolerations for pod assignment
  ## Ref: https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/
  ##
  tolerations:
            - key: "app"
              operator: "Equal"
              value: "elasticsearch"
              effect: "NoSchedule"
```


#modify the service type to be "LoadBalancer", we will default to external one for sake of simplicity, but you can change this to internal by modifying the annotation to "service.beta.kubernetes.io/azure-load-balancer-internal: "true""
```yaml
  service:
    ## coordinating-only service type
    ##
    type: LoadBalancer
    ## Elasticsearch tREST API port
    ##
    port: 9200
    ## Specify the nodePort value for the LoadBalancer and NodePort service types.
    ## ref: https://kubernetes.io/docs/concepts/services-networking/service/#type-nodeport
    ##
    # nodePort:
    ## Provide any additional annotations which may be required. This can be used to
    ## set the LoadBalancer service type to internal only.
    ## ref: https://kubernetes.io/docs/concepts/services-networking/service/#internal-load-balancer
    ##
    annotations
```

#modify autoscaling parameters
```yaml
  autoscaling:
    enabled: false
    minReplicas: 6
    maxReplicas: 12
```

4. The data nodes
#modify number of replicas to 6
```yaml
data:
  name: data
  ## Number of data node(s) replicas to deploy
  ##
  replicas: 6
```

#we repeat the same affinity and tolerations rules
```yaml
  affinity: 
          nodeAffinity:
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: topology.kubernetes.io/zone
                  operator: In
                  values:
                  - westus2-1
                  - westus2-2
                  - westus2-3
            requiredDuringSchedulingIgnoredDuringExecution:
              nodeSelectorTerms:
              - matchExpressions:
                - key: agentpool
                  operator: In
                  values:
                  - espoolz1
                  - espoolz2
                  - espoolz3

  ## Node labels for pod assignment
  ## Ref: https://kubernetes.io/docs/user-guide/node-selection/
  ##
  nodeSelector: {}

  ## Tolerations for pod assignment
  ## Ref: https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/
  ##
  tolerations:
            - key: "app"
              operator: "Equal"
              value: "elasticsearch"
              effect: "NoSchedule"
```

#modify autoscaling parameters
```yaml
 autoscaling:
    enabled: false
    minReplicas: 6
    maxReplicas: 18
```


### ElasticSearch Cluster Deployment

Now that we have configured the charts, we are ready to deploy the ES cluster 

1. Deploy the chart 

```shell 
#create a namespace for elasticsearch
$ kubectl create namespace elasticsearch
$ helm install elasticsearch-v1 bitnami/elasticsearch -n elasticsearch --values values.yaml
```

2. Validate the setup 

#watch the pods, it will take around 20 minutes for everything to be up and running  
```shell
$ kubectl get pods -n elasticsearch -w 

elasticsearch-v1-coordinating-only-6686cc5c8-b66sd   1/1     Running   0          21h
elasticsearch-v1-coordinating-only-6686cc5c8-jf5qd   1/1     Running   0          21h
elasticsearch-v1-coordinating-only-6686cc5c8-js9np   1/1     Running   0          21h
elasticsearch-v1-coordinating-only-6686cc5c8-nrnnq   1/1     Running   0          21h
elasticsearch-v1-coordinating-only-6686cc5c8-vtv6l   1/1     Running   0          21h
elasticsearch-v1-coordinating-only-6686cc5c8-xl8zs   1/1     Running   0          21h
elasticsearch-v1-data-0                              1/1     Running   0          21h
elasticsearch-v1-data-1                              1/1     Running   0          21h
elasticsearch-v1-data-2                              1/1     Running   0          21h
elasticsearch-v1-data-3                              1/1     Running   0          21h
elasticsearch-v1-data-4                              1/1     Running   0          21h
elasticsearch-v1-data-5                              1/1     Running   0          21h
elasticsearch-v1-master-0                            1/1     Running   0          21h
elasticsearch-v1-master-1                            1/1     Running   0          21h
elasticsearch-v1-master-2                            1/1     Running   0          21h
```

#lets inspect how the pods got distributed across the nodes 
```shell
$ kubectl get pods -n elasticsearch -o wide 

NAME                                                 READY   STATUS    RESTARTS   AGE   IP             NODE                               NOMINATED NODE   READINESS GATES
elasticsearch-v1-coordinating-only-6686cc5c8-b66sd   1/1     Running   0          21h   172.16.0.199   aks-espoolz3-41985791-vmss000001   <none>           <none>
elasticsearch-v1-coordinating-only-6686cc5c8-jf5qd   1/1     Running   0          21h   172.16.0.233   aks-espoolz2-41985791-vmss000000   <none>           <none>
elasticsearch-v1-coordinating-only-6686cc5c8-js9np   1/1     Running   0          21h   172.16.0.253   aks-espoolz2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-coordinating-only-6686cc5c8-nrnnq   1/1     Running   0          21h   172.16.0.109   aks-espoolz1-41985791-vmss000000   <none>           <none>
elasticsearch-v1-coordinating-only-6686cc5c8-vtv6l   1/1     Running   0          21h   172.16.0.141   aks-espoolz1-41985791-vmss000001   <none>           <none>
elasticsearch-v1-coordinating-only-6686cc5c8-xl8zs   1/1     Running   0          21h   172.16.0.184   aks-espoolz3-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-0                              1/1     Running   0          21h   172.16.0.173   aks-espoolz3-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-1                              1/1     Running   0          21h   172.16.1.18    aks-espoolz2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-2                              1/1     Running   0          21h   172.16.0.102   aks-espoolz1-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-3                              1/1     Running   0          21h   172.16.0.218   aks-espoolz3-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-4                              1/1     Running   0          21h   172.16.0.157   aks-espoolz1-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-5                              1/1     Running   0          21h   172.16.0.249   aks-espoolz2-41985791-vmss000000   <none>           <none>
elasticsearch-v1-master-0                            1/1     Running   0          21h   172.16.0.134   aks-espoolz1-41985791-vmss000001   <none>           <none>
elasticsearch-v1-master-1                            1/1     Running   0          21h   172.16.0.198   aks-espoolz3-41985791-vmss000001   <none>           <none>
elasticsearch-v1-master-2                            1/1     Running   0          21h   172.16.0.232   aks-espoolz2-41985791-vmss000000   <none>           <none>
```

#isn't this beautiful? :) with the power of affinity and topology rules we were able to
a. 6 coordinating/client nodes are spread evenly across nodes 
b. 3 Master nodes are deployed to 3 different nodes across 3 availability zones 
c. 6 data nodes are spread evenly across the nodes 


3. Lets check if the cluster is functioning properly 
#check the coordinating service external IP so we can test if things are working properly 
```shell
$ kubectl get svc elasticsearch-v1-coordinating-only -n elasticsearch

NAME                                 TYPE           CLUSTER-IP    EXTERNAL-IP    PORT(S)                         AGE
elasticsearch-v1-coordinating-only   LoadBalancer   10.0.210.19   20.98.122.48   9200:31512/TCP,9300:31026/TCP   21h

#lets store the value of the IP so we can use it later
$ esip=`kubectl get svc elasticsearch-v1-coordinating-only -n elasticsearch -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'`
```

#check the cluster health
```shell
$ curl "http://$esip:9200/_cluster/health?pretty"
```
#the output should like like the below
```yaml
{
  "cluster_name" : "elastic",
  "status" : "green",
  "timed_out" : false,
  "number_of_nodes" : 15,
  "number_of_data_nodes" : 6,
  "active_primary_shards" : 0,
  "active_shards" : 0,
  "relocating_shards" : 0,
  "initializing_shards" : 0,
  "unassigned_shards" : 0,
  "delayed_unassigned_shards" : 0,
  "number_of_pending_tasks" : 0,
  "number_of_in_flight_fetch" : 0,
  "task_max_waiting_in_queue_millis" : 0,
  "active_shards_percent_as_number" : 100.0
}
```yaml


#create an index called "test" with 3 shards and one replica
```shell
$ curl -XPUT "http://$esip:9200/test?pretty" -H 'Content-Type: application/json' -d'{"settings" : {"index" : {"number_of_shards" : 3, "number_of_replicas" : 1 }}}'

{
  "acknowledged" : true,
  "shards_acknowledged" : true,
  "index" : "test"
}

```
#validate the distribution of the shards, you should ideally see 3 shards in 3 AZs and 3 Replicas in 3 AZs 
```shell
$ curl http://$esip:9200/_cat/shards/test\?pretty\=true

test 1 p STARTED 0 208b 172.16.0.218 elasticsearch-v1-data-3
test 1 r STARTED 0 208b 172.16.0.173 elasticsearch-v1-data-0
test 2 p STARTED 0 208b 172.16.0.157 elasticsearch-v1-data-4
test 2 r STARTED 0 208b 172.16.1.18  elasticsearch-v1-data-1
test 0 p STARTED 0 208b 172.16.0.102 elasticsearch-v1-data-2
test 0 r STARTED 0 208b 172.16.0.249 elasticsearch-v1-data-5
```
#To validate the beauty of this, check out the pods again and do the correlation
```shell
$ kubectl get pods -o wide -n elasticsearch -l app=data 
NAME                      READY   STATUS    RESTARTS   AGE   IP             NODE                               NOMINATED NODE   READINESS GATES
elasticsearch-v1-data-0   1/1     Running   0          21h   172.16.0.173   aks-espoolz3-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-1   1/1     Running   0          21h   172.16.1.18    aks-espoolz2-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-2   1/1     Running   0          21h   172.16.0.102   aks-espoolz1-41985791-vmss000000   <none>           <none>
elasticsearch-v1-data-3   1/1     Running   0          21h   172.16.0.218   aks-espoolz3-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-4   1/1     Running   0          21h   172.16.0.157   aks-espoolz1-41985791-vmss000001   <none>           <none>
elasticsearch-v1-data-5   1/1     Running   0          21h   172.16.0.249   aks-espoolz2-41985791-vmss000000   <none>           <none>
```

# Summary
Now we have an ElasticSearch cluster deployed across 3 availability zones, the coordinating pods were exposed externally using a load balancer, and we created an index inside the cluster called "test".

Please continue to next section [Handling Failures](handling_failures.md)