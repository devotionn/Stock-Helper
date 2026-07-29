"""备份恢复测试"""
import pytest
from pathlib import Path

def test_create_backup(client):
    """测试创建备份"""
    r = client.post('/api/backup')
    assert r.status_code == 200
    data = r.json()
    assert 'path' in data
    assert 'file_count' in data

def test_list_backups(client):
    """测试列出备份"""
    client.post('/api/backup')
    r = client.get('/api/backup')
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1

def test_restore_with_bad_zip(client):
    """测试恢复无效文件"""
    import io
    from fastapi.testclient import TestClient
    # 创建一个假的zip文件
    fake_zip = io.BytesIO(b'not a zip file')
    r = client.post(
        '/api/backup/restore',
        files={'file': ('test.shbackup', fake_zip, 'application/octet-stream')},
    )
    assert r.status_code in [400, 500]
