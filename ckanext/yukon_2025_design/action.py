import ckan.plugins.toolkit as toolkit
import ckan.authz as authz
import ckan.model as model


def is_user_editor_of_org(org_id, user_id):
    capacity = authz.users_role_for_group_or_org(org_id, user_id)
    return capacity == "editor"


def is_user_admin_of_org(org_id, user_id):
    capacity = authz.users_role_for_group_or_org(org_id, user_id)
    return capacity == "admin"


def is_user_sysadmin(user_id):
    user = model.User.get(user_id)
    if user:
        return user.sysadmin
    return False


def can_view_internal_data(user, org_id):
    if not user:
        return False

    user_obj = model.User.get(user)
    if not user_obj:
        return False

    user_id = user_obj.id

    if is_user_sysadmin(user_id):
        return True
    if is_user_admin_of_org(org_id, user_id):
        return True
    if is_user_editor_of_org(org_id, user_id):
        return True
    return False


def _set_groups_list(context, data_dict):
    """
    Set the groupsfield in the data_dict from the groups_list
    """
    groups_list = data_dict.get("groups_list", False)
    if groups_list:
        groups = []
        if not isinstance(groups_list, list):
            groups_list = [groups_list]

        for group_id in groups_list:
            groups.append({"id": group_id})

        data_dict.pop("groups_list")
        data_dict["groups"] = groups


@toolkit.side_effect_free
@toolkit.chained_action
def package_show(up_func, context, data_dict):
    user = context.get("user")
    result = up_func(context, data_dict)
    org_id = result['organization']['id']
    if not can_view_internal_data(user, org_id):
        result.pop('internal_contact_name', None)
        result.pop('internal_contact_email', None)
        result.pop('internal_notes', None)
    
    return result

@toolkit.side_effect_free
@toolkit.chained_action
def package_search(up_func, context, data_dict):
    user = context.get("user")
    result = up_func(context, data_dict)
    pkg_dicts = result['results']

    for pkg_dict in pkg_dicts:
        org_id = pkg_dict['organization']['id']
        if not can_view_internal_data(user, org_id):
            pkg_dict.pop('internal_contact_name', None)
            pkg_dict.pop('internal_contact_email', None)
            pkg_dict.pop('internal_notes', None)

    return result


@toolkit.side_effect_free
@toolkit.chained_action
def current_package_list_with_resources(up_func, context, data_dict):
    user = context.get("user")
    results = up_func(context, data_dict)

    for result in results:
        org_id = result['organization']['id']
        if not can_view_internal_data(user, org_id):
            result.pop('internal_contact_name', None)
            result.pop('internal_contact_email', None)
            result.pop('internal_notes', None)

    return results


@toolkit.side_effect_free
@toolkit.chained_action
def package_create(up_func, context, data_dict):
    _set_groups_list(context, data_dict)

    return up_func(context, data_dict)


@toolkit.side_effect_free
@toolkit.chained_action
def package_update(up_func, context, data_dict):
    _set_groups_list(context, data_dict)

    return up_func(context, data_dict)