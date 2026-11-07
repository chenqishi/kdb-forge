py_env_config=./config/python_env_config.sh
source $py_env_config
run_config=$1
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
python cross_broder_access/backtest_online.py  batch_backtest_sql  config/mysql_conn_config.json $run_config  