import ckan.plugins.toolkit as toolkit
from ckanext.scheming.helpers import scheming_get_dataset_schema


def get_all_groups():
    """
    Returns a list of all groups in CKAN.
    """
    try:
        groups = toolkit.get_action('group_list')(
            {'ignore_auth': True}, {'all_fields': True}
        )  # Bypass auth
        return groups
    except toolkit.ObjectNotFound:
        return []


def group_is_empty(data_dict, group_name, dataset_type):
    """
    Returns True if the group is empty, False otherwise.
    """
    dataset_fields = scheming_get_dataset_schema(dataset_type)["dataset_fields"]
    group_fields = []
    for field in dataset_fields:
        try:
            if field["group_name"] == group_name:
                if data_dict.get(field["field_name"]):
                    group_fields.append(field["field_name"])
                if field["field_name"] == "tag_string":
                    if data_dict.get("tags"):
                        group_fields.append("tags")
                if field["field_name"] == "groups_list":
                    if data_dict.get("groups"):
                        group_fields.append("groups")
        except KeyError:
            pass
    if len(group_fields) == 0:
        return True
    return False
