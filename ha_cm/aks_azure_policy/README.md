## AKS With Azure Policy

In this section, i'll demonstrate how you AKS can deploy AKS while having a Policy for tags as part of Azure Policy.

If you're not familier with Azure policy then please check the docs [here](https://docs.microsoft.com/en-us/azure/governance/policy/overview).


#### Demo - AKS with Azure Policy

When deploying AKS today you can pass tags to the  AKS resource during provisioning, and AKS will pass the tags to the infrastructure resources group (MC_), but not to the resources, as such we the "enforce" policy for tags should be on the resource group level rather than the resoruces.

Also we will also have a custom name for the infrastructure resource group. 


1. Apply an *enforce* policy on the resource groups
 
Luckily the Azure Policy has great examples on how to do this, so follow this [doc](https://docs.microsoft.com/en-us/azure/governance/policy/samples/enforce-tag-on-resource-groups
)

2. Apply an *append* policy for the resources underneath the infrastructure resource group 
   
Again there is an example in the Policy docs to accomplish this, follow this [doc](https://docs.microsoft.com/en-us/azure/governance/policy/samples/apply-tag-default-value)

3. *Optionally* you can have a remediate policy for all the resources that were created before and have no tags, follow the doc [here](https://docs.microsoft.com/en-us/azure/governance/policy/how-to/remediate-resources)


4. Now you can deploy your AKS cluster, assuming that what you enforced is a tagName=CostCenter and a TagValue=String, then the below should work.


```shell
#define your variables 
location=westeurope
rg=ignite
infra_rg=aks-ignite-policy_nodes
clustername=aks-ignite-policy
vmsize=Standard_B2s
version="1.14.8"

#create the resource group 
az group create -n $rg -l $location

#create the cluster 
az aks create \
    --resource-group $rg \
    --node-resource-group $infra_rg \
    --name $clustername \
    --node-count 1 \
    --tags CostCenter=Finance \
    --location $location

#once the cluster is done, you can check if the tags are passed to the infra_rg (later you can also check on the resources if the tags were passed)

az group show -n $infra_rg -o json --query "tags"
{
  "CostCentetr": "Finance"
}

```
   

