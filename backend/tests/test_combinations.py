"""组合分析API测试"""
import pytest

def test_create_combination(client):
    """测试创建常用组合"""
    r = client.post('/api/combinations', json={'name': '测试组合', 'module_ids': [0, 1, 7, 8]})
    assert r.status_code == 200
    data = r.json()
    assert data['name'] == '测试组合'
    assert data['module_ids'] == [0, 1, 7, 8]

def test_list_combinations(client):
    """测试获取组合列表"""
    # 先创建
    client.post('/api/combinations', json={'name': '组合A', 'module_ids': [0, 1]})
    client.post('/api/combinations', json={'name': '组合B', 'module_ids': [2, 3]})
    r = client.get('/api/combinations')
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2

def test_delete_combination(client):
    """测试删除组合"""
    r = client.post('/api/combinations', json={'name': '待删除', 'module_ids': [0]})
    cid = r.json()['id']
    r = client.delete(f'/api/combinations/{cid}')
    assert r.status_code == 200
