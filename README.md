[![Tests](https://github.com/datopian/ckanext-yukon-2025-design/workflows/Tests/badge.svg?branch=main)](https://github.com/datopian/ckanext-yukon-2025-design/actions)

# ckanext-yukon-2025-design

This extension is a CKAN extension that provides a new design for the Yukon 2025 project.


## Requirements

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.11.0 | yes    |

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

## API Documentation: `package_set_featured`

### Overview

The `package_set_featured` API is a CKAN extension action that allows sysadmins to manage featured datasets. It ensures that exactly three datasets are marked as "featured" while removing the "featured" status from previously featured datasets. The API includes robust validation to ensure that only valid datasets of type `data` can be featured.

---

### What It Does

1. **Sets Three Datasets as Featured**:
   - Marks exactly three datasets as "featured" by setting the `is_featured` flag to `True`.

2. **Removes Previous Featured Datasets**:
   - Removes the "featured" status from all previously featured datasets.

3. **Validates Input**:
   - Ensures that exactly three dataset IDs or names are provided.
   - Checks that all provided datasets exist in CKAN.
   - Ensures that all provided datasets are of type `data`.

4. **Error Handling**:
   - If the process fails, the API restores the "featured" status of previously featured datasets to maintain data integrity.

---

### How It Works

1. **Authorization Check**:
   - The API verifies that the user making the request is a sysadmin using the `is_user_sysadmin` function.
   - If the user is not a sysadmin, the API raises a `NotAuthorized` error.

2. **Input Validation**:
   - Extracts the `dataset_ids` from the `data_dict` parameter.
   - Ensures that exactly three dataset IDs are provided. If not, a `ValidationError` is raised.

3. **Dataset Validation**:
   - Uses the `package_show` action to check if each dataset exists.
   - Ensures that all datasets are of type `data`. If any dataset does not exist or is not of type `data`, a `ValidationError` is raised with a descriptive error message.

4. **Backup Current Featured Datasets**:
   - Fetches all currently featured datasets using the `package_search` action.
   - Stores their IDs in a list (`previous_featured_ids`) to allow restoration in case of failure.

5. **Remove "Featured" Status from Current Featured Datasets**:
   - Iterates through the `previous_featured_ids` and removes the "is_featured" flag from each dataset using the `package_update` action.

6. **Set "Featured" Status for New Datasets**:
   - Iterates through the provided dataset IDs.
   - Ensures all required fields (`internal_contact_email`, `internal_contact_name`, `license_id`) are present in the dataset.
   - Sets the "is_featured" flag to `True` for each dataset using the `package_update` action.

7. **Error Handling**:
   - If any error occurs during the process, the API restores the "is_featured" flag for the previously featured datasets to maintain consistency.
   - Raises a `ValidationError` with a descriptive error message if the process fails.

8. **Success Response**:
   - If the process completes successfully, the API returns a success message: `{"success": True, "message": "Featured datasets updated successfully."}`

---

### Requirements

1. **Sysadmin Privileges**:
   - Only users with sysadmin privileges can use this API. The `is_user_sysadmin` function checks the user's role.

2. **Valid Input**:
   - The `data_dict` parameter must include a key `dataset_ids` with exactly three dataset IDs or names. Example:
     ```json
     {
         "dataset_ids": ["dataset_id_1", "dataset_id_2", "dataset_id_3"]
     }
     ```

3. **Dataset Existence**:
   - All provided datasets must exist in CKAN. If any dataset does not exist, the API will raise a `ValidationError`.

4. **Dataset Type**:
   - All provided datasets must be of type `data`. If any dataset is not of type `data`, the API will raise a `ValidationError`.

5. **Required Fields in Datasets**:
   - The datasets being updated must include the following fields:
     - `internal_contact_email`
     - `internal_contact_name`
     - `license_id`
   - If any of these fields are missing, the API assigns default values:
     - `internal_contact_email`: `''` (empty string)
     - `internal_contact_name`: `''` (empty string)
     - `license_id`: `'notspecified'`

6. **CKAN Actions**:
   - The API relies on the following CKAN actions:
     - `package_show`: To fetch dataset details.
     - `package_search`: To fetch currently featured datasets.
     - `package_update`: To update dataset details.

7. **Error Handling**:
   - If the process fails, the API restores the "is_featured" flag for previously featured datasets to maintain consistency.

---

### Example Usage

**API Call Using `curl`:**
```bash
curl -X POST http://localhost:5000/api/3/action/package_set_featured \
    -H "Authorization: YOUR_SYSADMIN_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "dataset_ids": ["dataset_id_1", "dataset_id_2", "dataset_id_3"]
    }'
```

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
