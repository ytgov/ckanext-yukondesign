import ckan.plugins.toolkit as toolkit


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