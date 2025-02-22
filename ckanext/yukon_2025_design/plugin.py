import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.yukon_2025_design.action as action


class Yukon2025DesignPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IActions)

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "yukon_2025_design")

    def get_actions(self):
        return {
            'package_show': action.package_show,
            'package_search': action.package_search,
            'current_package_list_with_resources': action.current_package_list_with_resources
        }

