from unittest.mock import MagicMock, patch

import pytest

from app.db import archive


@pytest.mark.parametrize('scope, columns', [
    ('title', ['c.capstone_title']),
    ('keyword', ['k.capstone_keywords']),
    ('all', ['c.capstone_title', 'k.capstone_keywords', 'search_author.aut_last_name)']),
    ('invalid', ['c.capstone_title', 'k.capstone_keywords', 'search_author.aut_last_name)']),
])
def test_search_scope_filters_count_and_results(scope, columns):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = {'total': 1}
    cursor.fetchall.return_value = [{'capstone_id': 1}]
    with patch.object(archive, 'db_connect', return_value=connection):
        rows, total = archive.get_archive_capstones(
            search="farmer's market", search_scope=scope, page=2,
        )

    assert total == 1
    assert rows == [{'capstone_id': 1}]
    assert cursor.execute.call_count == 2
    for index, call in enumerate(cursor.execute.call_args_list):
        sql, params = call.args
        assert sql.count('ILIKE %s') == len(columns)
        for column in columns:
            assert column + ' ILIKE %s' in sql
        assert "farmer's market" not in sql
        expected = ["%farmer's market%"] * len(columns)
        assert params == expected + ([12, 12] if index else [])


def test_scope_without_search_does_not_hide_records():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = {'total': 0}
    cursor.fetchall.return_value = []
    with patch.object(archive, 'db_connect', return_value=connection):
        archive.get_archive_capstones(search_scope='keyword')

    for call in cursor.execute.call_args_list:
        assert 'ILIKE' not in call.args[0]
