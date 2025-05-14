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
