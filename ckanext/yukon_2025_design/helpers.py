import datetime
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

      
def recently_updated_open_informations():
    """
    Returns a list of 3 recently updated open informations.
    """
    try:
        result = toolkit.get_action('package_search')(
            {'ignore_auth': True},
            {'fq': 'type:information', 'sort': 'metadata_modified desc', 'rows': 3}
        )  # Bypass auth
        # Drop all the fields except the ones we need: title, name and type
        packages = []
        for item in result['results']:
            package = {}
            package['title'] = item['title']
            package['name'] = item['name']
            package['type'] = item['type']
            packages.append(package)
        return packages
    except toolkit.ObjectNotFound:
        return []
    

def recently_added_access_requests():
    """
    Returns a list of 3 recently added access requests.
    """
    try:
        result = toolkit.get_action('package_search')(
            {'ignore_auth': True},
            {'fq': 'type:access-requests', 'sort': 'metadata_created desc', 'rows': 3}
        )  # Bypass auth
        # Drop all the fields except the ones we need: title, name and type
        packages = []
        for item in result['results']:
            package = {}
            package['title'] = item['title']
            package['name'] = item['name']
            package['type'] = item['type']
            packages.append(package)
        return packages
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


def get_current_year():
    """Returns the current year as an integer."""
    return datetime.datetime.now().year

def dataset_type_title(dataset_type):
  """Convert dataset type to a human-readable title."""
  mapping = {
    "pia-summaries": "Privacy impact assessment summaries",
    "information": "Open information",
    "data": "Open Data",
    "access-requests": "Completed Access to Information requests"
  }
  return mapping.get(dataset_type, dataset_type)