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


def get_featured_datasets():
    """
    Returns a list of all featured datasets.
    """
    try:
        result = toolkit.get_action('package_search')(
            {'ignore_auth': True},
            {'fq': 'is_featured:true', 'rows': 1000}
        )  # Bypass auth
        return result['results']
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


def dataset_type_title(dataset_type, plural=True):
  """Convert dataset type to a human-readable title, supporting singular and plural."""
  mapping = {
    "pia-summaries": ("Privacy Impact Assessment summary", "Privacy Impact Assessment summaries"),
    "information": ("Open information", "Open information"),
    "data": ("Open data", "Open data"),
    "access-requests": (
      "Completed access to information request",
      "Completed access to information requests"
    )
  }

  title_pair = mapping.get(dataset_type, (dataset_type, dataset_type))
  return title_pair[1] if plural else title_pair[0]


def dataset_type_menu_title(dataset_type):
    """Convert dataset type to a human-readable title for menus."""
    mapping = {
        "pia-summaries": "a PIA summary",
        "information": "open information",
        "data": "open data",
        "access-requests": " a completed access request"
    }
    return mapping.get(dataset_type, dataset_type)


def add_matomo_siteid_to_context():
    """
    Adds the Matomo site ID to the template context.
    This is used for tracking purposes.
    """
    # Get the Matomo site ID from the CKAN configuration
    matomo_siteid = toolkit.config.get('ckan.matomo_siteid', '1')
    # Return the Matomo site ID for direct use in templates
    return matomo_siteid


def pop_zip_resource(pkg):
    '''Finds the zip resource in a package's resources, removes it from the
    package and returns it. NB the package doesn't have the zip resource in it
    any more.
    '''
    zip_res = None
    non_zip_resources = []
    for res in pkg.get('resources', []):
        if res.get('downloadall_metadata_modified'):
            zip_res = res
        else:
            non_zip_resources.append(res)
    pkg['resources'] = non_zip_resources
    return zip_res