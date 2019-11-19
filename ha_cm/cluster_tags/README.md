## Create an AKS cluster with TAGs

AKS now have the ability to pass the tags to the infrastructure resource group (MC_), note that the tags will not be passed to the resources.

Also AKS now gives you the ability to influence the name of the infrastructure resource group, note the resource group has to be new, it can't be an existing one.

```shell
$ az aks create --help
....
    
--node-resource-group                     : The node resource group is the resource group where
                                            all customer's resources will be created in, such as virtual machines.
                    
....
--tags                                    : Space-separated tags in 'key[=value]' format. Use ''
                                                to clear existing tags.
....                                                
```

Example
```shell
#create a cluster with tags and a custom name for the infrastructure resource group 
$ az aks create \
    --resource-group ignite-tags \
    --node-resource-group ignite-tags-nodes-rg \
    --name ignite-tags \
    --generate-ssh-keys \
    --node-count 1 \
    --tags project=ignite \
    --location westeurope

#check the tags on the infra resource group 
$ az group show -n ignite-tags-nodes-rg -o json --query "tags"
{
  "project": "ignite"
}
```


If you're interested in how we can enforce tags and work with Azure Policy, then check the AKS with Azure Policy section.


