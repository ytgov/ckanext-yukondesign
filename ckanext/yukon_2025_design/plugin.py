import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.yukon_2025_design.action as action
import ckanext.yukon_2025_design.helpers as helpers
from ckanext.yukon_2025_design.auth import package_delete_sysadmin_only


class Yukon2025DesignPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.ITranslation)

    def i18n_directory(self):
        return 'ckanext/yukon_2025_design/i18n'

    def i18n_domain(self):
        return 'ckanext-yukon_2025_design'

    def i18n_locales(self):
        # Return a list of supported locale codes, e.g. ['en', 'fr']
        return ['en', 'fr']
    
    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('assets', 'yukon_2025_design')

    def get_actions(self):
        return {
            'package_show': action.package_show,
            'package_search': action.package_search,
            'current_package_list_with_resources': (
                action.current_package_list_with_resources
            ),
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
            'recently_updated_open_informations': (
                helpers.recently_updated_open_informations
            ),
            'recently_added_access_requests': (
                helpers.recently_added_access_requests
            ),
            'group_is_empty': helpers.group_is_empty,
            'get_featured_datasets': helpers.get_featured_datasets,
            'get_current_year': helpers.get_current_year,
            'dataset_type_title': helpers.dataset_type_title,
            'dataset_type_menu_title': helpers.dataset_type_menu_title,
            'matomo_siteid': helpers.add_matomo_siteid_to_context
        }
