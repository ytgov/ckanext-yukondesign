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
    # If the form omitted the field entirely, leave existing groups unchanged.
    # If the field is present but empty, treat that as an invalid submission
    # and raise a ValidationError so the UI shows a required-field message.
    if "groups_list" not in data_dict:
        return

    gl = data_dict.get("groups_list")
    empty = False
    if isinstance(gl, str) and not gl.strip():
        empty = True
    elif isinstance(gl, (list, tuple)) and not any(bool(x) for x in gl):
        empty = True
    if empty:
        raise toolkit.ValidationError({"groups_list": ["Missing value"]})

    groups_list = gl
    if isinstance(groups_list, str):
        groups_list = [groups_list]

    # Build groups list, filtering out any empty values
    groups = []
    for group_id in [g for g in groups_list if g]:
        try:
            group = get_action("group_show")(context, {"id": group_id})
        except Exception:
            # Ignore invalid group ids rather than crashing the update
            continue
        groups.append({key: group.get(key) for key in ("id", "name", "title")})

    data_dict.pop("groups_list", None)
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


def package_set_featured(context, data_dict):
    """
    Sets three datasets as featured and removes previous featured datasets.
    Ensures that exactly three dataset IDs are provided.
    If the process fails, retains the previous featured datasets.

    Only sysadmins are allowed to use this API.

    :param context: The context dictionary provided by CKAN
    :type context: dict
    :param data_dict: The data dictionary containing the dataset IDs
    :type data_dict: dict

    :returns: A success message or raises an error
    :rtype: str
    """
    # Check if the user is a sysadmin
    user = context.get('user')
    if not user or not is_user_sysadmin(user):
        raise toolkit.NotAuthorized("Only sysadmins can use this API.")

    # Extract dataset IDs from data_dict
    dataset_ids = data_dict.get('dataset_ids')
    if not dataset_ids or len(dataset_ids) != 3:
        raise toolkit.ValidationError(
            "Exactly three dataset IDs or names must be provided."
        )

    # Check if all provided datasets exist and are of type 'data'
    non_existent_datasets = []
    invalid_type_datasets = []
    package_objects = {}  # Store package objects for later use
    
    for dataset_id in dataset_ids:
        try:
            dataset = toolkit.get_action('package_show')(
                {'ignore_auth': True},
                {'id': dataset_id}
            )
            # Check if the dataset type is 'data'
            if dataset.get('type') != 'data':
                invalid_type_datasets.append(dataset_id)
            else:
                # Get the actual package object from the database
                package_obj = model.Package.get(dataset['id'])
                if package_obj:
                    # Use the original dataset_id as key, not the UUID
                    package_objects[dataset_id] = package_obj
        except toolkit.ObjectNotFound:
            non_existent_datasets.append(dataset_id)

    if non_existent_datasets:
        raise toolkit.ValidationError(
            f"The following datasets do not exist: "
            f"{', '.join(non_existent_datasets)}"
        )

    if invalid_type_datasets:
        raise toolkit.ValidationError(
            f"The following datasets are not of type 'data': "
            f"{', '.join(invalid_type_datasets)}"
        )

    try:
        import logging
        log = logging.getLogger(__name__)
        log.info(f"Starting package_set_featured for datasets: {dataset_ids}")
        
        # Fetch all current featured datasets
        current_featured = toolkit.get_action('package_search')(
            {'ignore_auth': True},
            {'fq': 'is_featured:True', 'rows': 1000}
        )['results']
        
        log.info(f"Found {len(current_featured)} currently featured datasets")

        # Backup current featured dataset IDs
        previous_featured_ids = [pkg['id'] for pkg in current_featured]
        previous_featured_objects = {}
        
        # Get package objects for current featured datasets
        for pkg_id in previous_featured_ids:
            package_obj = model.Package.get(pkg_id)
            if package_obj:
                previous_featured_objects[pkg_id] = package_obj

        # Remove the "is_featured" flag from all current featured datasets
        for pkg_id in previous_featured_ids:
            package_obj = previous_featured_objects.get(pkg_id)
            if package_obj:
                log.info(f"Removing featured flag from package {pkg_id}")
                # Update the extras directly without changing metadata_modified
                _update_package_extra(package_obj, 'is_featured', 'False')

        # Set the "is_featured" flag for the new datasets
        for dataset_id in dataset_ids:
            package_obj = package_objects.get(dataset_id)
            if package_obj:
                log.info(f"Setting featured flag for package {dataset_id}")
                log.info(f"Pkg ID: {package_obj.id}, Name: {package_obj.name}")
                # Update the extras directly without changing metadata_modified
                _update_package_extra(package_obj, 'is_featured', 'True')
            else:
                log.error(f"No package object found for {dataset_id}")

        log.info("Committing database changes")
        # Commit the changes
        model.repo.commit()
        
        # Manually update search index for affected packages
        # This ensures search queries work without updating metadata_modified
        # We need to do this AFTER commit so package_show returns updated extras
        import ckan.lib.search as search
        package_ids_to_reindex = set(previous_featured_ids) | set([package_objects[did].id for did in dataset_ids])
        
        log.info(f"Reindexing {len(package_ids_to_reindex)} packages in search index")
        
        # Get the search index backend
        search_backend = search.index_for('package')
        
        for pkg_id in package_ids_to_reindex:
            try:
                # Fetch the updated package data after commit
                package_dict = toolkit.get_action('package_show')(
                    {'ignore_auth': True}, {'id': pkg_id}
                )
                is_featured_value = package_dict.get('is_featured', 'NOT_SET')
                log.info(f"Reindexing package {pkg_id}, is_featured={is_featured_value}")
                
                # Update the search index with the current package data
                search_backend.index_package(package_dict, defer_commit=False)
                log.info(f"Successfully reindexed package {pkg_id}")
            except Exception as e:
                log.error(f"Failed to reindex package {pkg_id}: {e}")
                import traceback
                log.error(traceback.format_exc())
                # Continue with other packages even if one fails
                continue
        
        # Commit all changes to Solr
        search_backend.commit()
        log.info("Search index committed")

        return {
            "success": True,
            "message": "Featured datasets updated successfully."
        }

    except Exception as e:
        # Rollback any changes
        model.repo.rollback()
        raise toolkit.ValidationError(
            f"Failed to set featured datasets: {str(e)}"
        )


def _update_package_extra(package_obj, key, value):
    """
    Helper function to update a package extra field without changing
    metadata_modified.
    
    :param package_obj: The package object
    :param key: The extra field key
    :param value: The new value for the extra field
    """
    import logging
    log = logging.getLogger(__name__)
    
    log.info(f"Updating package {package_obj.id} extra {key} to {value}")
    
    # Try to find the specific extra we want to update
    existing_extra = model.Session.query(model.PackageExtra).filter_by(
        package_id=package_obj.id,
        key=key
    ).first()
    
    if existing_extra:
        log.info(f"Found existing extra {key} = {existing_extra.value}")
        # Always update the value, even if it's 'False'
        # This ensures the search index can properly filter on the field
        old_value = existing_extra.value
        existing_extra.value = value
        log.info(f"Updated extra {key} from {old_value} to {value}")
    else:
        log.info(f"No existing extra {key} found, creating new one")
        # Always create the extra, even if value is 'False'
        new_extra = model.PackageExtra(
            package_id=package_obj.id,
            key=key,
            value=value
        )
        model.Session.add(new_extra)
        log.info(f"Added new extra: {key} = {value}")
    
    # Flush to ensure the change is in the session
    model.Session.flush()
    log.info("Session flushed")
    
    # Verify the extra was created/updated
    verify_extra = model.Session.query(model.PackageExtra).filter_by(
        package_id=package_obj.id,
        key=key
    ).first()
    
    if verify_extra:
        log.info(f"Verification: extra {key} = {verify_extra.value}")
    else:
        log.warning(f"Verification: extra {key} not found after update!")
    
    log.info(f"Package {package_obj.id} extra {key} update completed")
