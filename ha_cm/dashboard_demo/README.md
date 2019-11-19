## Safe Kubernetes Dashboard
Although k8s dashboard is helpful in some cases, its always been a risk to run it, in this walkthough i'll provide you with some options of how you can make it safer. 

AKS has a secured by default dashboard which is exposed only behind a proxy and run behined a slimmed down service account, please check the docs [here](https://docs.microsoft.com/en-us/azure/aks/kubernetes-dashboard).

#### Option#1 No Dashboard
Yes, if you don't use it remove it, AKS provides the ability to disable the dashboard after the cluster was provisioned.

```shell
#check of the dashboard is running
$ kubectl get pods -n kube-system | grep "dashboard"
kubernetes-dashboard-cc4cc9f58-whmhv   1/1     Running   0          30d

#disable the dashboard addon
az aks disable-addons -a kube-dashboard -g ResourceGroup -n ClusterName

#dashboard should be gone 
kubectl get pods -n kube-system | grep "dashboard"

```

###### Note 
Follow this [issue](https://github.com/Azure/AKS/issues/1074) where we are working on having the  feature of creating an AKS cluster with no Dashboard. 

#### Option#2 Use Service Accounts to access the dashboard
If its an absolute necessity to run the dashboard then you can access using service account tokens, more on the topic can be found [here](https://github.com/kubernetes/dashboard/blob/master/docs/user/access-control/creating-sample-user.md
)

```shell
#First edit your dashboard deployment
$ kubectl edit deployments -n kube-system kubernetes-dashboard
```

Add the below lines to your deployment (yes it will persist)
```yaml
      - args:
        - --authentication-mode=token
        - --enable-insecure-login
```

Your dashboard deployment  will look similar to the below
```yaml
      containers:
      - args:
        - --authentication-mode=token
        - --enable-insecure-login
        image: aksrepos.azurecr.io/mirror/kubernetes-dashboard-amd64:v1.10.1
        imagePullPolicy: IfNotPresent
        livenessProbe:
          failureThreshold: 3
          httpGet:
            path: /
            port: 9090
            scheme: HTTP
```

Now that we enabled token auth, we can proceed with creating the service account
```shell
# Create the service account in the current namespace 
# (we assume default)
kubectl create serviceaccount my-dashboard-sa

# Give that service account root on the cluster
kubectl create clusterrolebinding my-dashboard-sa \
  --clusterrole=cluster-admin \
  --serviceaccount=default:my-dashboard-sa

# Find the secret that was created to hold the token for the SA
kubectl get secrets

# Show the contents of the secret to extract the token
kubectl describe secret my-dashboard-sa-token-tqknr

#use the token to access the dashboard
```

Notes:
1. more information on the 2 arguments you added can be found [here](https://github.com/kubernetes/dashboard/blob/master/docs/common/dashboard-arguments.md
) . for reference:
* authentication-mode	token	Enables authentication options that will be reflected on login screen. Supported values: token, basic. Note that basic option should only be used if apiserver has '--authorization-mode=ABAC' and '--basic-auth-file' flags set.
* enable-insecure-login	false	When enabled, Dashboard login view will also be shown when Dashboard is not served over HTTPS.

2. Accessing the dashboard using your AAD identity is WiP and can be tracked [here](https://github.com/MicrosoftDocs/azure-docs/issues/23789)