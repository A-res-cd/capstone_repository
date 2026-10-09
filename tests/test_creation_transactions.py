from unittest.mock import MagicMock

import pytest

from app.db import capstones


@pytest.mark.parametrize('people_fail', [False, True])
def test_create_uses_one_transaction(monkeypatch, people_fail):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(20,), (10,), (30,)]
    connect = MagicMock(return_value=conn)
    monkeypatch.setattr(capstones, 'db_connect', connect)
    monkeypatch.setattr(capstones, 'log_audit', MagicMock())

    def execute(sql, params):
        if people_fail and 'INSERT INTO Author' in sql:
            raise RuntimeError('People insert failed')

    cursor.execute.side_effect = execute
    success, result = capstones.create_capstone_project(
        None, 1, 1, 'Title', 2026, 'uploads/test.pdf', '1st',
        capstone_keywords='test', authors=[],
        adviser={'first': 'Test', 'last': 'Adviser'},
    )

    connect.assert_called_once_with()
    assert success is not people_fail
    if people_fail:
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()
    else:
        assert result == 20
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    conn.close.assert_called_once_with()
