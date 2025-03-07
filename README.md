[![Tests](https://github.com/datopian/ckanext-yukon-2025-design/workflows/Tests/badge.svg?branch=main)](https://github.com/datopian/ckanext-yukon-2025-design/actions)

# ckanext-yukon-2025-design

This extension is a CKAN extension that provides a new design for the Yukon 2025 project.


## Requirements

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.11.1 and earlier | yes    |

## Deployment

To deploy this extension, you need to have a CKAN instance running. You can follow the [official documentation](https://docs.ckan.org/en/latest/maintaining/installing/index.html) to install CKAN.

Additional information can be found in the [Deployment documentation](DEPLOYMENT.md).

## Installation

**TODO:** Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-yukon-2025-design:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/datopian/ckanext-yukon-2025-design.git
    cd ckanext-yukon-2025-design
    pip install -e .
	pip install -r requirements.txt

3. Add `yukon-2025-design` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Config settings

None at present

## Developer installation

To install ckanext-yukon-2025-design for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/datopian/ckanext-yukon-2025-design.git
    cd ckanext-yukon-2025-design
    pip install -e .
    pip install -r dev-requirements.txt


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## Releasing a new version of ckanext-yukon-2025-design

If ckanext-yukon-2025-design should be available on PyPI you can follow these steps to publish a new version:

1. Update the version number in the `pyproject.toml` file. See [PEP 440](http://legacy.python.org/dev/peps/pep-0440/#public-version-identifiers) for how to choose version numbers.

2. Make sure you have the latest version of necessary packages:

    pip install --upgrade setuptools wheel twine

3. Create a source and binary distributions of the new version:

       python -m build && twine check dist/*

   Fix any errors you get.

4. Upload the source distribution to PyPI:

       twine upload dist/*

5. Commit any outstanding changes:

       git commit -a
       git push

6. Tag the new release of the project on GitHub with the version number from
   the `setup.py` file. For example if the version number in `setup.py` is
   0.0.1 then do:

       git tag 0.0.1
       git push --tags

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
