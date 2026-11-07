import atexit
import json
import logging
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool


class MySQLConnector:
    def __init__(self, config_path):
        if not hasattr(self, 'pool'):  # 确保连接池只初始化一次
            self._init_pool(config_path)

    def _init_pool(self, config_path):
        if config_path is None:
            return
        self._load_config(config_path)
        try:
            self.pool = MySQLConnectionPool(
                pool_name="mysql_connection_pool",
                pool_size=5,
                host= self._host,
                database= self._database,
                user= self._user,
                password=self._password
            )
            logging.info('Connection pool created successfully')
            atexit.register(self._close_pool)  # Register the _close method to be called at exit
        except Error as e:
            logging.error(f"Error while creating connection pool: {e}")
            raise e

    def get_connection(self):
        try:
            return self.pool.get_connection()
        except Error as e:
            logging.error(f"Error while getting connection: {e}")
            return None

    def close_connection(self, connection, cursor):
        try:
            if connection.is_connected():
                cursor.close()
                connection.close()
        except Error as e:
            logging.error(f"Error while closing connection: {e}")

    def _close_pool(self):
        try:
            self.pool._remove_connections()
            logging.info('Connection pool closed successfully')
        except Error as e:
            logging.error(f"Error while closing connection pool: {e}")


    def _load_config(self, config_path):
        with open(config_path) as f:
            self.config = json.load(f)
        self._host = self.config.get("host")
        self._database = self.config.get("database")
        self._user = self.config.get("user")
        self._password = self.config.get("password")

