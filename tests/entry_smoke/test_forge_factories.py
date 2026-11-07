"""Preserve original forge factories and native count without external I/O."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from kdb.services.forge_compat import adapter
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService


@pytest.mark.parametrize('explicit,default,test_index,expected', [('explicit','default','test','explicit'),(None,'default','test','default'),(None,None,'test','test'),(None,None,None,None)])
def test_original_factory_index_priority(monkeypatch, explicit, default, test_index, expected):
    cfg={'engine_config_path':'engine.json','embedding_config_path':'embedding.json','default_index_name':default,'test_index_name':test_index}
    monkeypatch.setattr(adapter,'load_config',Mock(return_value=cfg))
    monkeypatch.setattr(KnowledgeService,'_load_legacy_search_cfg',Mock(return_value={'check_duplicate':False,'multimodal_prefix':'files/'}))
    repo=KnowledgeRepository(SimpleNamespace(index_name='engine-default',_impl=None))
    factory=Mock(return_value=repo)
    embedding=Mock()
    monkeypatch.setattr(adapter,'KnowledgeRepository',factory)
    monkeypatch.setattr(adapter,'build_embedding_client',Mock(return_value=embedding))
    service=KnowledgeService.from_config('config.json',index_name=explicit)
    factory.assert_called_once_with(engine_config_path='engine.json',default_index=expected)
    assert service._embedding is embedding
    assert service.multimodal_prefix=='files/' and service.check_duplicate is False


@pytest.mark.parametrize('field',['legacy_search_config_path','search_config_path'])
def test_original_legacy_config_aliases(tmp_path,field):
    config=tmp_path/'legacy.json'
    config.write_text(json.dumps({'check_duplicate':False}))
    assert KnowledgeService._load_legacy_search_cfg({field:str(config)})=={'check_duplicate':False}
    assert KnowledgeService._load_legacy_search_cfg({field:str(tmp_path/'missing.json')})=={}


def test_original_count_factory_disables_all_ensure(monkeypatch):
    import kdb.es.engine as engine_module
    cfg={'engine_config_path':'engine.json','default_index_name':'chosen','embedding_config_path':'must-not-read'}
    monkeypatch.setattr(adapter,'load_config',Mock(return_value=cfg))
    engine=SimpleNamespace(index_name='chosen',_impl=None)
    factory=Mock(return_value=engine)
    monkeypatch.setattr(engine_module,'RoutedLegacyEngine',factory)
    monkeypatch.setattr(adapter,'build_embedding_client',Mock(side_effect=AssertionError('embedding forbidden')))
    service=KnowledgeService.from_count_config('config.json')
    factory.assert_called_once_with(config_path='engine.json',index_name='chosen',ensure_index=False,extra_params={'ensure_index_on_init':False})
    assert service.engine is engine and service._embedding is None


def test_original_count_validation_and_native_dsl():
    engine=SimpleNamespace(index_name='default',_impl=None,count_by_query=Mock(return_value=7))
    service=KnowledgeService(KnowledgeRepository(engine),None)
    assert service.get_from_type_count('chosen','2026-01-01 00:00:00','2026-02-01 00:00:00','document')==(True,7,'')
    engine.count_by_query.assert_called_once_with('chosen',{'bool':{'filter':[{'term':{'quality_level':'high'}},{'term':{'from_type':'document'}},{'range':{'insert_time':{'gte':'2026-01-01 00:00:00','lte':'2026-02-01 00:00:00'}}}]}},require_complete=True)
    engine.count_by_query.reset_mock()
    assert service.get_from_type_count(None)==(True,0,'')
    assert service.get_from_type_count('a,b')==(False,0,'统计失败')
    assert service.get_from_type_count('chosen',start='invalid')==(False,0,'统计失败')
    engine.count_by_query.assert_not_called()
