export PYTHONUTF8=1
export PYTHONPATH=../..
python-lambda-local -f lambda_handler -t 30 lambda_function.py event.json
