"""Thin standalone category protocol over SearchDataInterface's existing methods."""


class CategoryClient:
    def __init__(self, service_url="", update_interval=36000):
        from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
        self._interface = SearchDataInterface.__new__(SearchDataInterface)
        self._interface.category_service_url = service_url or ""
        self._interface.category_update_time_interval = update_interval
        self._interface.all_client_category_dict = {}
        self._interface.category_update_time_dict = {}

    @property
    def service_url(self):
        return self._interface.category_service_url

    @service_url.setter
    def service_url(self, value):
        self._interface.category_service_url = value

    @property
    def update_interval(self):
        return self._interface.category_update_time_interval

    @update_interval.setter
    def update_interval(self, value):
        self._interface.category_update_time_interval = value

    @property
    def all_client_category_dict(self):
        return self._interface.all_client_category_dict

    @all_client_category_dict.setter
    def all_client_category_dict(self, value):
        self._interface.all_client_category_dict = value

    @property
    def category_update_time_dict(self):
        return self._interface.category_update_time_dict

    @category_update_time_dict.setter
    def category_update_time_dict(self, value):
        self._interface.category_update_time_dict = value

    def load_category_map_dict(self, client, user=None):
        return self._interface.load_category_map_dict(client, user)

    def map_cate_name_to_id(self, client, category_name):
        return self._interface.map_cate_name_to_id(client, category_name)

    def get_category_parent_chain(self, client, cate_id=None, cate_name=None):
        return self._interface.get_category_parent_chain(client, cate_id, cate_name)
