import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.yukon_2025_design.action as action
import ckanext.yukon_2025_design.helpers as helpers
from ckanext.yukon_2025_design.auth import package_delete_sysadmin_only
from ckan.lib.jobs import DEFAULT_QUEUE_NAME

from ckan import model

from .tasks import update_zip

log = __import__('logging').getLogger(__name__)


class Yukon2025DesignPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IDomainObjectModification)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.ITranslation)

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "yukon_2025_design")

    def notify(self, entity, operation):
        u'''
        Send a notification on entity modification.

        :param entity: instance of module.Package.
        :param operation: 'new', 'changed' or 'deleted'.
        '''
        if operation == 'deleted':
            return

        log.debug(u'{} {} \'{}\''
                  .format(operation, type(entity).__name__, entity.name))
        # We should regenerate zip if these happen:
        # 1 change of title, description etc (goes into package.json)
        # 2 add/change/delete resource metadata
        # 3 change resource data by upload (results in URL change)
        # 4 change resource data by remote data
        # BUT not:
        # 5 if this was just an update of the Download All zip itself
        #   (or you get an infinite loop)
        #
        # 4 - we're ignoring this for now (ideally new data means a new URL)
        # 1&2&3 - will change package.json and notify(res) and possibly
        #         notify(package) too
        # 5 - will cause these notifies but package.json only in limit places
        #
        # SO if package.json (not including Package Zip bits) remains the same
        # then we don't need to regenerate zip.
        if isinstance(entity, model.Package):
            enqueue_update_zip(entity.name, entity.id, operation)
        elif isinstance(entity, model.Resource):
            if entity.extras.get('downloadall_metadata_modified'):
                # this is the zip of all the resources - no need to react to
                # it being changed
                log.debug('Ignoring change to zip resource')
                return
            dataset = entity.related_packages()[0]
            enqueue_update_zip(dataset.name, dataset.id, operation)
        else:
            return


    def enqueue_update_zip(dataset_name, dataset_id, operation):
    # skip task if the dataset is already queued
        queue = DEFAULT_QUEUE_NAME
        jobs = toolkit.get_action('job_list')(
            {'ignore_auth': True}, {'queues': [queue]})
        if jobs:
            for job in jobs:
                if not job['title']:
                    continue
                match = re.match(
                    r'DownloadAll \w+ "[^"]*" ([\w-]+)', job[u'title'])
                if match:
                    queued_dataset_id = match.groups()[0]
                    if dataset_id == queued_dataset_id:
                        log.info('Already queued dataset: {} {}'
                                .format(dataset_name, dataset_id))
                        return

        # add this dataset to the queue
        log.debug(u'Queuing job update_zip: {} {}'
                .format(operation, dataset_name))

        toolkit.enqueue_job(
            update_zip, [dataset_id],
            title=u'DownloadAll {} "{}" {}'.format(operation, dataset_name,
                                                dataset_id),
            queue=queue)
    

    def get_actions(self):
        return {
            'package_show': action.package_show,
            'package_search': action.package_search,
            'current_package_list_with_resources': action.current_package_list_with_resources,
            'package_create': action.package_create,
            'package_update': action.package_update,
            'package_set_featured': action.package_set_featured,
        }

    def get_auth_functions(self):
        return {
            'package_delete': package_delete_sysadmin_only
        }

    def get_helpers(self):
        return {
            'get_all_groups': helpers.get_all_groups,
            'recently_updated_open_informations': helpers.recently_updated_open_informations,
            'recently_added_access_requests': helpers.recently_added_access_requests,
            'group_is_empty': helpers.group_is_empty,
            'get_featured_datasets': helpers.get_featured_datasets,
            'get_current_year': helpers.get_current_year,
            'dataset_type_title' : helpers.dataset_type_title,
            'dataset_type_menu_title' : helpers.dataset_type_menu_title,
            'matomo_siteid': helpers.add_matomo_siteid_to_context,
            'downloadall__pop_zip_resource': helpers.pop_zip_resource,
        }
