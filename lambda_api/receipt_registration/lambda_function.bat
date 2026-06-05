
chcp 65001
set PYTHONUTF8=1
set PYTHONPATH=..\..
python-lambda-local -f lambda_handler -t 30 lambda_function.py event.json