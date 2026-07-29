"""组合分析测试"""
import pytest

def test_create_analysis_pending(client):
    """测试创建分析任务返回pending"""
    # 先给模块0写入一些文字
    r = client.get('/api/modules/0')
    rev = r.json()['revision']
    client.put('/api/modules/0', json={'text_content': '测试分析内容', 'revision': rev})

    # 创建分析
    r = client.post('/api/analysis', json={
        'module_ids': [0],
        'analysis_request': '测试',
        'combination_name': '测试组合'
    })
    assert r.status_code == 202
    data = r.json()
    assert 'id' in data
    assert data['status'] in ['pending', 'running']

def test_get_analysis_detail(client):
    """测试获取分析详情"""
    # 先创建
    r = client.get('/api/modules/0')
    rev = r.json()['revision']
    client.put('/api/modules/0', json={'text_content': '测试', 'revision': rev})
    r = client.post('/api/analysis', json={
        'module_ids': [0],
        'analysis_request': '',
        'combination_name': ''
    })
    aid = r.json()['id']
    # 获取详情
    r = client.get(f'/api/analysis/{aid}/detail')
    assert r.status_code == 200
    data = r.json()
    assert 'analysis' in data
    assert 'snapshots' in data
