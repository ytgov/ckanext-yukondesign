import ckan.plugins.toolkit as toolkit


def package_delete_sysadmin_only(context, data_dict):
    """
    Auth function to allow only sysadmins to delete datasets.
    """
    # Check if user has sysadmin role
    if not toolkit.check_access('sysadmin', context):
        raise toolkit.NotAuthorized(
            "Only sysadmins can delete datasets."
        )
    # Allow deletion
    return context


def yukon_matomo_sync_usage_data_sysadmin_only(context, data_dict):
    """Allow only sysadmins to trigger Matomo sync through the API."""
    if not toolkit.check_access('sysadmin', context):
        raise toolkit.NotAuthorized(
            "Only sysadmins can trigger Matomo usage sync."
        )
    return {'success': True}
