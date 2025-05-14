# -*- coding: utf-8 -*-
from setuptools import setup

# Note: Do not add new arguments to setup(), instead add setuptools
# configuration options to setup.cfg, or any other project information
# to pyproject.toml
# See https://github.com/ckan/ckan/issues/8382 for details

setup(
    # If you are changing from the default layout of your extension, you may
    # have to change the message extractors, you can read more about babel
    # message extraction at
    # http://babel.pocoo.org/docs/messages/#extraction-method-mapping-and-configuration
    # Removed message_extractors as it is not supported by setuptools
    entry_points="""
        [ckan.plugins]
        yukondesign = ckanext.yukon.plugin:Yukon2025DesignPlugin

        [babel.extractors]
        ckan = ckan.lib.extract:extract_ckan
        """
)
