Deployment documentation
=======================

## Requirements

1. `ckanext-scheming` extension must be installed and configured. This extension is used to create custom datasets and resource schemas. You can find more information about this extension in the [official documentation](https://github.com/ckan/ckanext-scheming/tree/master)

## Configuration settings

We need to setup the following configuration settings in the CKAN configuration file (`/etc/ckan/default/ckan.ini`), or in the environment variables:

```
CKAN__PLUGINS="scheming_datasets yukon_2025_design envvars"
CKAN__LICENSES_GROUP_URL=file:///srv/app/src_extensions/ckanext-yukon-2025-design/licenses-yukon.json
CKAN___SCHEMING__DATASET_SCHEMAS="ckanext.yukon_2025_design:data_schema.yaml ckanext.yukon_2025_design:information_schema.yaml ckanext.yukon_2025_design:access-requests_schema.yaml ckanext.yukon_2025_design:pia-summaries_schema.yaml"
```

License file is provided in the `licenses-yukon.json` file in the repository. You can change the path to the file if needed.