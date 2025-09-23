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
            {'fq': 'is_featured:true', 'rows': 1000}
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
        
        # Verify the changes were applied
        log.info("Verifying changes were applied...")
        for dataset_id in dataset_ids:
            try:
                package_dict = toolkit.get_action('package_show')(
                    {'ignore_auth': True}, {'id': dataset_id}
                )
                is_featured_value = package_dict.get('is_featured', 'NOT_SET')
                log.info(f"Package {dataset_id} featured={is_featured_value}")
            except Exception as e:
                log.error(f"Failed to verify package {dataset_id}: {e}")
        
        # Manually update search index for affected packages
        # This ensures search queries work without updating metadata_modified
        try:
            from ckan.lib.search import rebuild
            package_ids_to_reindex = (
                list(previous_featured_ids) + list(dataset_ids)
            )
            for pkg_id in package_ids_to_reindex:
                try:
                    # Use rebuild function to force reindex
                    rebuild(package_id=pkg_id, only_missing=False, force=True)
                except Exception:
                    # Try alternative method if rebuild fails
                    try:
                        import ckan.lib.search as search
                        package_dict = toolkit.get_action('package_show')(
                            {'ignore_auth': True}, {'id': pkg_id}
                        )
                        search_backend = search.get_backend()
                        search_backend.update_dict(package_dict)
                    except Exception:
                        pass  # Skip this package if both methods fail
        except Exception as index_error:
            # Log the error but don't fail the operation
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"Failed to update search index: {index_error}")

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
    
    # First, let's see what extras already exist
    existing_extras = model.Session.query(model.PackageExtra).filter_by(
        package_id=package_obj.id
    ).all()
    log.info(f"Package {package_obj.id} has {len(existing_extras)} extras")
    for extra in existing_extras:
        log.info(f"  - {extra.key} = {extra.value}")
    
    # Try to find the specific extra we want to update
    existing_extra = model.Session.query(model.PackageExtra).filter_by(
        package_id=package_obj.id,
        key=key
    ).first()
    
    if existing_extra:
        log.info(f"Found existing extra {key} = {existing_extra.value}")
        if value in ['False', 'false', '']:
            # Remove the extra if setting to false
            log.info(f"Deleting extra {key}")
            model.Session.delete(existing_extra)
        else:
            # Update existing extra
            old_value = existing_extra.value
            existing_extra.value = value
            log.info(f"Updated extra {key} from {old_value} to {value}")
    else:
        log.info(f"No existing extra {key} found")
        if value not in ['False', 'false', '']:
            # Create new extra only if value is truthy
            log.info(f"Creating new extra {key} with value {value}")
            new_extra = model.PackageExtra(
                package_id=package_obj.id,
                key=key,
                value=value
            )
            model.Session.add(new_extra)
            log.info(f"Added new extra: {new_extra.key} = {new_extra.value}")
    
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
