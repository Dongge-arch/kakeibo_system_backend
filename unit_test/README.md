# Tests

Run the active backend tests from the repository root:

```sh
python -m pytest -q unit_test
```

On Windows, `unit_test\run_all_tests_simple.bat` runs the same suite.

Old Lambda event samples and their Windows scripts are retained under
`unit_test/legacy_lambda/` for reference. They are not part of the active test
suite or the deployed Lambda packages. Each function source directory contains
its own `lambda_handler.py`; deployment copies that file to an isolated package.
