Deployment documentation
=======================

## Requirements

1. `ckanext-scheming` extension must be installed and configured. This extension is used to create custom datasets and resource schemas. You can find more information about this extension in the [official documentation](https://github.com/ckan/ckanext-scheming/tree/master)

## Configuration settings

We need to setup the following configuration settings in the CKAN configuration file (`/etc/ckan/default/ckan.ini`), or in the environment variables:

```env
# Pugin order is very important`
ckan.plugins = activity yukondesign scheming_datasets envvars
ckan.auth.anon_create_dataset = false
ckan.auth.create_unowned_dataset = false
ckan.auth.allow_dataset_collaborators = true
ckan.auth.allow_admin_collaborators = true
ckan.licenses_group_url = file:///srv/app/src/ckanext-yukondesign/licenses-yukon.json
ckan.dataset.create_on_ui_requires_resources = false
# Put Matomo siteid here (4 is used for the Datopian test environment)
ckan.matomo_siteid = 4
ckan.locale_default = en
ckan.locales_offered = en fr
ckan.scheming.dataset_schemas = ckanext.yukondesign:data_schema.yaml ckanext.yukondesign:information_schema.yaml ckanext.yukondesign:access-requests_schema.yaml ckanext.yukondesign:pia-summaries_schema.yaml
```

License file is provided in the `licenses-yukon.json` file in the repository. You can change the path to the file if needed.
