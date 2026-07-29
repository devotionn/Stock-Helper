"""模块API基本测试"""
import pytest

def test_health_check(client):
    """测试健康检查"""
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'

def test_list_modules(client):
    """测试获取12个模块卡片"""
    r = client.get('/api/modules')
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12
    assert data[0]['module_name'] == '一周策略'
    assert data[11]['module_name'] == '操作建议'

def test_get_module_draft(client):
    """测试获取模块草稿"""
    r = client.get('/api/modules/0')
    assert r.status_code == 200
    data = r.json()
    assert data['module_id'] == 0
    assert data['module_name'] == '一周策略'

def test_update_module_draft(client):
    """测试更新模块文字"""
    # 先获取revision
    r = client.get('/api/modules/0')
    rev = r.json()['revision']
    # 更新
    r = client.put('/api/modules/0', json={'text_content': '测试内容', 'revision': rev})
    assert r.status_code == 200
    assert r.json()['revision'] == rev + 1
    # 验证
    r = client.get('/api/modules/0')
    assert r.json()['text_content'] == '测试内容'

def test_concurrency_protection(client):
    """测试并发覆盖保护"""
    r = client.get('/api/modules/0')
    rev = r.json()['revision']
    # 用错误的revision应该返回409
    r = client.put('/api/modules/0', json={'text_content': '冲突测试', 'revision': rev + 999})
    assert r.status_code == 409
