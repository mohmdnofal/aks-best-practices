# Azure Kubernetes Service Security Best Practices 
This section contains the slides, demos, and the recording for the security webinar that was delivered on the 20th of Nov. more work will be added to this section and the repo in general. 

## slides
download the slides [here](aks_best_practices_security_v4.pptx)

## Secure CosmosCats Demo
We were tasked to host a simple Node application called CosmosCats inside an AKS cluster, the application uploads and views cat pictures from/to a Cosmos DB.

We will spin up an AKS Cluster with AAD integratioin, enable and work with network policies, work with Pod Identities, key vault integration, work on the APP GW ingress controllers and some other fun things.

Lets get started!

1. Spin up an AKS cluster 

We start by defining our variables 
```shell
rg=sec-webinar # your Resource Group Name
location=westeurope # your preferred Azure region 
clusterName=aks-sec-webinar #your cluser name 
vnetName=aks-vnet #the vent name 
vnetCidr=10.0.0.0/23 #the CIDR for the vnet 
clusterSubnet=aks-subnet #the name of the subnet where your cluster will reside 
clusterPrefix=10.0.0.0/24 #the IP block for the cluster 
adminUN=mohamman #SSH username
nodeSize=Standard_B2s #VM SKU 
k8sVersion=1.14.8 #k8s version 
logId=/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/k8s/providers/Microsoft.OperationalInsights/workspaces/k8s-logs-workspace #create a workspace for monitoring 
SubnetId=/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/$rg/providers/Microsoft.Network/virtualNetworks/aks-vnet/subnets/$clusterSubnet
#follow this tutorial in order to create the AAD applications https://docs.microsoft.com/en-us/azure/aks/azure-ad-integration 
ServerApplicationID="XXXXXXX-XXXX-XXXX-XXXXX-XXXXXXXXXXXXX" #the AAD Server Application ID
ServerApplicationSecret="XXXXXXXXXXXXXXXXXXXXXXXX" #the AAD Server Application secret 
TenantID="XXXXXXXX-XXXXXX-XXXX-XXXX-XXXXXXXX" #the AAD tenant ID
ClientApplicationID="XXXXX-XXXXXX-XXXX-XXXX-XXXXX" #the AAD client application ID
```

**Hint** if you have trouble with getting the AAD integration to work as it requires the admin consent, then either create a new AAD tenant under a test subscription, or skip the AAD part.

#create the resource group, vnet, the aks subnet, and finally 
```shell
#create the resource group
$ az group create -n $rg -l $location

#create vnet
$ az network vnet create --name $vnetName --resource-group $rg --address-prefixes $vnetCidr --subnet-name $clusterSubnet --subnet-prefix $clusterPrefix --location $location
```

#create the cluster 
```shell
$ az aks create \
  --resource-group $rg \
  --name $clusterName \
  --generate-ssh-keys \
  --aad-server-app-id $ServerApplicationID \
  --aad-server-app-secret $ServerApplicationSecret \
  --aad-client-app-id $ClientApplicationID \
  --aad-tenant-id $TenantID \
  --admin-username $adminUN \
  --enable-addons monitoring \
  --workspace-resource-id $logId \
  --kubernetes-version $k8sVersion \
  --load-balancer-sku standard \
  --location $location  \
  --network-plugin "azure" \
  --network-policy "calico" \
  --node-count 3  \
  --node-vm-size $nodeSize \
  --nodepool-name default \
  --vnet-subnet-id $SubnetId \
  --service-cidr 172.16.0.0/24 \
  --docker-bridge-address 172.17.0.1/24 \
  --dns-service-ip 172.16.0.10 \
  --tags Project=SecurityWebinar 
# --service-principal \ #uncomment the below 2 lines if you want to use pre-craeted SPs 
# --client-secret \
```


2. Configure AAD and RBAC roles 

#access the cluster 
```shell
#get creds for the admin (this overrides RBAC so you can setup RBAC :) )
#access the cluster to create the roles 
$ az aks get-credentials --resource-group $rg --name $clusterName --admin

#test
$ kubectl get nodes
```

#lets see RBAC in action, assign your user admin role and switch to user credintials 
```shell
#create role binding for admins, CHANGE THE GROUP ID in the "rbac-aad-xxx.yaml" file to your user group id 
$ kubectl apply -f rbac/rbac-aad-admins-group-rolebinding.yaml

#get the USER credentials  
$ az aks get-credentials --resource-group $rg --name $clusterName 

#test, you should be redirected to a login page as RBAC is in action now, all goes well command will return the nodes
$ kubectl get nodes
```

#now we need to create a Namespace to host our application, we will add resource quotas to it, and we will assign the owner team admin access on the namespace.
```shell
#create the namespace 
$ kubectl create namespace webinar

#apply resource quotas to the namespace to avoid DoS attacks 
$ kubectl apply -f ns/webinar-rq.yaml

#create a role for who can access the namespace 
$ kubectl apply -f rbac/role-webinar-namespace.yaml
$ kubectl apply -f rbac/rolebinding-webinar-namespace.yaml #change the group ID to whatever group ID of your choice
```

3. Install the keyvault flex volume driver and the pod identity tools 

The application will require credentials to login to Cosmos, so we will use key vault to store the secrets. in order to pull the secrets to k8s, we have the following tools to install.


#install the keyvault flexvol https://github.com/Azure/kubernetes-keyvault-flexvol
```shell
#install the kevault integration (already done)
$ kubectl create -f https://raw.githubusercontent.com/Azure/kubernetes-keyvault-flexvol/master/deployment/kv-flexvol-installer.yaml

#verify it works 
$ kubectl  get pods -n kv 
```

#install the Pod Identity tool in order to be able to assign pods with identities to access the key vault
```shell
$ kubectl apply -f https://raw.githubusercontent.com/Azure/aad-pod-identity/master/deploy/infra/deployment-rbac.yaml

#verify 
$ kubectl get pods 
```

4. Create a cosmos DB in the same location where the AKS cluster is, the API should be "SQL" 
https://docs.microsoft.com/en-us/azure/cosmos-db/create-cosmosdb-resources-portal

#Get the URI and the KEY to access cosmos from the APP  
```shell
Cosmos_URI=https://COSMOS_DB_NAME.documents.azure.com:443/
Cosmos_KEY=LZwwH0vAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

5. Create an Azure Keyvault and upload your secrets to it

```shell
kvName=webinar-kv
#create the keyvault 
$ az keyvault create -n $kvName -g $rg -l $location

#create your secrets 
$ az keyvault secret set \
  --vault-name $kvName \
  --name CosmosdbEndpoint \
  --value $Cosmos_URI

$ az keyvault secret set \
  --vault-name $kvName \
  --name CosmosdbKey \
  --value $Cosmos_KEY
``` 

6. We need to create a managed service identity and assign it access to the Key Vault

```shell
#create an identity to interact with the key vault 
$ az identity create -g $rg -n keyvault-webinar -o json
{
  "clientId": "xxxxx-xxxx-xxx-xxx-xxxx",
  "id": "/subscriptions/000000000000000/resourcegroups/sec-webinar/providers/Microsoft.ManagedIdentity/userAssignedIdentities/keyvault-webinar",
  "location": "westeurope",
  "name": "keyvault-webinar",
  "principalId": "00000000000000000000000000",
  "resourceGroup": "sec-webinar",
  ..
  "type": "Microsoft.ManagedIdentity/userAssignedIdentities"
}

#create the variables
principal="YOUR_MSI_Principal_ID"
keyvaultID="your keyvault resource ID"
identity_client="Client_ID_from_the_above_output"
identity_id=""id" from the above command"

# Assign Reader Role to new Identity for your Key Vault
$ az role assignment create --role Reader --assignee $principal --scope $keyvaultID
# set policy to access keys in your Key Vault
$ az keyvault set-policy -n $kvName --key-permissions get --spn $identity_client
# set policy to access secrets in your Key Vault
$ az keyvault set-policy -n $kvName --secret-permissions get --spn $identity_client
# set policy to access certs in your Key Vault
$ az keyvault set-policy -n $kvName --certificate-permissions get --spn $identity_client



#give the cluster service principal the permission to be the MSI operator (the assignee below is your cluster service principle id)
$ az aks show -g $rg -n $clusterName --query servicePrincipalProfile.clientId -o tsv

$ az role assignment create --role "Managed Identity Operator" \
  --assignee CLUSTER_SERVICE_PRINCIPAL_ID --scope /subscriptions/xxxxxxxxxxxxxxxx/resourcegroups/sec-webinar/providers/Microsoft.ManagedIdentity/userAssignedIdentities/keyvault-webinar
```


7. We need to create the identity and the mapping inside the cluster 
   
```shell
###before applying the below go to "aadpodidentity.yaml" and change the "ResourceID" to the "identity_id" and the "ClientID" to the "identity_client" values 
$ kubectl apply -f identity/aadpodidentity.yaml
$ kubectl apply -f identity/aadpodidentitybinding.yaml
```

8. Create your application 

```shell
##create the app, in the bottom of the file you need to change the "subscriptionid" and the "tenantid" to your subscription values 
$ kubectl apply -f app/cosmoscats.yaml
$ kubectl expose pod cosmoscats -n webinar --type=LoadBalancer --port 80

#check the app is working
$ kubectl get pods -l app=cosmoscats -n webinar
$ kubectl get svc -n webinar 

##test the app 
$ curl SERVICE_IP 
OR 
just type the IP of the service in the browser 
```


9. lets apply some network policies 

```shell
#apply a deny all network policy
$ kubectl apply -f np/default-deny-all.yaml

#test, the application should not be working now
$ curl SERVICE_IP

#allow inbound on port 80
$ kubectl apply -f np/allow-external-traffic.yaml

#now things should work
$ curl SERVICE_IP
```


10. Now we need to add ingress  on top using  the Application Gateway Ingress  Controller 

```shell
#we need to create an Applicatoin Gateway and install the ingress, please follow the below  tutorial
https://github.com/Azure/application-gateway-kubernetes-ingress
```

Now we create  the ingress resource
```shell
#check if its working
$ kubectl get pods -l app=ingress-azure

#create secret  (AGIC doesn't support keyvault flex volume yet)
$ kubectl create secret tls comsoscats-tls --key app/key.pem --cert app/cert.pem -n webinar

#create ingress rule (change the host name to any CNAME of your choice inside the below file)
$ kubectl apply -f app/ing-cosmoscats.yaml

#check agic logs 
$ kubectl logs agic-ingress-azure-784cf6c866-9prgc

#open browser to check!
cosmoscats.linux-jo.com
```

11. remove everything, this concludes the demo!