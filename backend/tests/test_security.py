"""安全相关测试：会话令牌、Host校验"""
import pytest

def test_get_session_token(client):
    """测试获取会话令牌"""
    r = client.get('/api/session')
    assert r.status_code == 200
    assert 'token' in r.json()
    assert len(r.json()['token']) > 20

def test_health_check(client):
    """测试健康检查"""
    r = client.get('/api/health')
    assert r.status_code == 200

def test_settings_masked_key(client):
    """测试设置API不返回明文密钥"""
    r = client.get('/api/settings')
    assert r.status_code == 200
    data = r.json()
    assert 'ai_api_key' not in data
    assert 'has_api_key' in data
    assert 'masked_api_key' in data
