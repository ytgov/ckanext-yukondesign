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
            {
                'fq': 'type:information',
                'sort': 'metadata_modified desc',
                'rows': 3
            }
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
            {
                'fq': 'type:access-requests',
                'sort': 'metadata_created desc',
                'rows': 3
            }
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
        # First try the search index
        result = toolkit.get_action('package_search')(
            {'ignore_auth': True},
            {
                'fq': 'is_featured:true AND type:data',
                'rows': 1000,
                'sort': 'metadata_created desc'
            }
        )
        
        # If search returns results, use them
        if result['results']:
            return result['results']
        
        # Fallback: Query database directly for packages with is_featured extra
        import ckan.model as model
        featured_packages = []
        
        # Get all packages with is_featured extra set to True
        extras_query = model.Session.query(model.PackageExtra).filter(
            model.PackageExtra.key == 'is_featured',
            model.PackageExtra.value == 'True'
        ).all()
        
        for extra in extras_query:
            try:
                # Get the full package data
                package_dict = toolkit.get_action('package_show')(
                    {'ignore_auth': True},
                    {'id': extra.package_id}
                )
                # Only include if it's a data type package
                if package_dict.get('type') == 'data':
                    featured_packages.append(package_dict)
            except Exception:
                # Skip packages that can't be shown
                continue
        
        return featured_packages
        
    except Exception as e:
        # Log the error for debugging
        import logging
        log = logging.getLogger(__name__)
        log.error(f"Error getting featured datasets: {e}")
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
    """Convert dataset type to a human-readable title for menus, translated."""
    _ = toolkit._
    mapping = {
        "pia-summaries": _("a PIA summary"),
        "information": _("open information"),
        "data": _("open data"),
        "access-requests": _("a completed access request")
    }
    return mapping.get(dataset_type, _(dataset_type))


def add_matomo_siteid_to_context():
    """
    Adds the Matomo site ID to the template context.
    This is used for tracking purposes.
    """
    # Get the Matomo site ID from the CKAN configuration
    matomo_siteid = toolkit.config.get('ckan.matomo_siteid', '1')
    # Return the Matomo site ID for direct use in templates
    return matomo_siteid
