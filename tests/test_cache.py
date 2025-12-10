import pytest
from unittest.mock import patch, MagicMock
import os


class TestNoOpCache:
    """Test the _NoOpCache fallback implementation."""

    def test_noop_cache_get_returns_none(self):
        """NoOp cache always returns None for get."""
        from cache import _NoOpCache
        
        cache = _NoOpCache()
        assert cache.get("any_key") is None
        assert cache.get("another_key") is None

    def test_noop_cache_set_returns_false(self):
        """NoOp cache always returns False for set."""
        from cache import _NoOpCache
        
        cache = _NoOpCache()
        assert cache.set("key", "value") is False
        assert cache.set("key", {"complex": "data"}, ttl_seconds=60) is False

    def test_noop_cache_delete_returns_false(self):
        """NoOp cache always returns False for delete."""
        from cache import _NoOpCache
        
        cache = _NoOpCache()
        assert cache.delete("key") is False
        assert cache.delete("nonexistent") is False

    def test_noop_cache_get_or_set_always_calls_creator(self):
        """NoOp cache always calls creator since get always misses."""
        from cache import _NoOpCache
        
        cache = _NoOpCache()
        creator_calls = []
        
        def creator():
            creator_calls.append(1)
            return "computed_value"
        
        # First call
        result1 = cache.get_or_set("key", creator)
        assert result1 == "computed_value"
        assert len(creator_calls) == 1
        
        # Second call - still calls creator (no caching)
        result2 = cache.get_or_set("key", creator)
        assert result2 == "computed_value"
        assert len(creator_calls) == 2

    def test_noop_cache_get_or_set_with_none_value(self):
        """NoOp cache doesn't cache None values from creator."""
        from cache import _NoOpCache
        
        cache = _NoOpCache()
        
        def creator():
            return None
        
        result = cache.get_or_set("key", creator)
        assert result is None


class TestBMemcachedCache:
    """Test the _BMemcachedCache wrapper."""

    def test_bmemcached_get_success(self):
        """BMemcached get returns cached value."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.get.return_value = {"data": "value"}
        
        cache = _BMemcachedCache(mock_client)
        result = cache.get("test_key")
        
        assert result == {"data": "value"}
        mock_client.get.assert_called_once_with("test_key")

    def test_bmemcached_get_exception_returns_none(self):
        """BMemcached get returns None on exception."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection failed")
        
        cache = _BMemcachedCache(mock_client)
        result = cache.get("test_key")
        
        assert result is None

    def test_bmemcached_set_success(self):
        """BMemcached set returns True on success."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.set.return_value = True
        
        cache = _BMemcachedCache(mock_client)
        result = cache.set("key", "value", ttl_seconds=60)
        
        assert result is True
        mock_client.set.assert_called_once_with("key", "value", time=60)

    def test_bmemcached_set_exception_returns_false(self):
        """BMemcached set returns False on exception."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.set.side_effect = Exception("Write failed")
        
        cache = _BMemcachedCache(mock_client)
        result = cache.set("key", "value")
        
        assert result is False

    def test_bmemcached_delete_success(self):
        """BMemcached delete returns True on success."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.delete.return_value = True
        
        cache = _BMemcachedCache(mock_client)
        result = cache.delete("key")
        
        assert result is True
        mock_client.delete.assert_called_once_with("key")

    def test_bmemcached_delete_exception_returns_false(self):
        """BMemcached delete returns False on exception."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.delete.side_effect = Exception("Delete failed")
        
        cache = _BMemcachedCache(mock_client)
        result = cache.delete("key")
        
        assert result is False


class TestBuildClient:
    """Test the _build_client factory function."""

    def test_build_client_no_env_vars(self):
        """Returns NoOpCache when env vars not set."""
        from cache import _build_client, _NoOpCache
        
        with patch.dict(os.environ, {}, clear=True):
            # Remove all MEMCACHEDCLOUD vars
            for key in list(os.environ.keys()):
                if key.startswith('MEMCACHEDCLOUD'):
                    del os.environ[key]
            
            client = _build_client()
            assert isinstance(client, _NoOpCache)

    def test_build_client_partial_env_vars(self):
        """Returns NoOpCache when only some env vars set."""
        from cache import _build_client, _NoOpCache
        
        with patch.dict(os.environ, {
            'MEMCACHEDCLOUD_SERVERS': 'server1:11211',
            # Missing username and password
        }, clear=True):
            client = _build_client()
            assert isinstance(client, _NoOpCache)

    def test_build_client_empty_servers(self):
        """Returns NoOpCache when servers list is empty after parsing."""
        from cache import _build_client, _NoOpCache
        
        with patch.dict(os.environ, {
            'MEMCACHEDCLOUD_SERVERS': '   ,   ,   ',  # Only whitespace/commas
            'MEMCACHEDCLOUD_USERNAME': 'user',
            'MEMCACHEDCLOUD_PASSWORD': 'pass',
        }, clear=True):
            with patch('cache.bmemcached', MagicMock()):
                client = _build_client()
                assert isinstance(client, _NoOpCache)

    @patch('cache.bmemcached')
    def test_build_client_connection_exception(self, mock_bmemcached):
        """Returns NoOpCache when connection fails."""
        from cache import _build_client, _NoOpCache
        
        mock_bmemcached.Client.side_effect = Exception("Connection refused")
        
        with patch.dict(os.environ, {
            'MEMCACHEDCLOUD_SERVERS': 'server1:11211',
            'MEMCACHEDCLOUD_USERNAME': 'user',
            'MEMCACHEDCLOUD_PASSWORD': 'pass',
        }, clear=True):
            client = _build_client()
            assert isinstance(client, _NoOpCache)

    @patch('cache.bmemcached')
    def test_build_client_success(self, mock_bmemcached):
        """Returns BMemcachedCache when configured correctly."""
        from cache import _build_client, _BMemcachedCache
        
        mock_client = MagicMock()
        mock_bmemcached.Client.return_value = mock_client
        
        with patch.dict(os.environ, {
            'MEMCACHEDCLOUD_SERVERS': 'server1:11211,server2:11211',
            'MEMCACHEDCLOUD_USERNAME': 'user',
            'MEMCACHEDCLOUD_PASSWORD': 'pass',
        }, clear=True):
            client = _build_client()
            assert isinstance(client, _BMemcachedCache)
            mock_bmemcached.Client.assert_called_once_with(
                ['server1:11211', 'server2:11211'], 'user', 'pass'
            )


class TestKeyGenerators:
    """Test cache key generation functions."""

    def test_make_key_simple(self):
        """make_key creates namespaced key."""
        from cache import make_key, _NAMESPACE
        
        key = make_key("policy", 123)
        assert key == f"{_NAMESPACE}:policy:123"

    def test_make_key_multiple_parts(self):
        """make_key handles multiple parts."""
        from cache import make_key, _NAMESPACE
        
        key = make_key("a", "b", "c", 1, 2, 3)
        assert key == f"{_NAMESPACE}:a:b:c:1:2:3"

    def test_policy_key(self):
        """policy_key generates correct key."""
        from cache import policy_key, _NAMESPACE
        
        key = policy_key(42)
        assert key == f"{_NAMESPACE}:policy:42"

    def test_student_summary_key(self):
        """student_summary_key generates correct key."""
        from cache import student_summary_key, _NAMESPACE
        
        key = student_summary_key(5, "2025-09-01")
        assert key == f"{_NAMESPACE}:student_summary:5:2025-09-01"

    def test_schedule_preview_key_without_week(self):
        """schedule_preview_key without week."""
        from cache import schedule_preview_key, _NAMESPACE
        
        key = schedule_preview_key(10)
        assert key == f"{_NAMESPACE}:schedule_preview:10"

    def test_schedule_preview_key_with_week(self):
        """schedule_preview_key with week."""
        from cache import schedule_preview_key, _NAMESPACE
        
        key = schedule_preview_key(10, "2025-09-01")
        assert key == f"{_NAMESPACE}:schedule_preview:10:2025-09-01"

    def test_outputs_index_key(self):
        """outputs_index_key generates correct key."""
        from cache import outputs_index_key, _NAMESPACE
        
        key = outputs_index_key()
        assert key == f"{_NAMESPACE}:outputs:index:summary"

    def test_all_students_weeks_key(self):
        """all_students_weeks_key generates correct key."""
        from cache import all_students_weeks_key, _NAMESPACE
        
        key = all_students_weeks_key()
        assert key == f"{_NAMESPACE}:outputs:all_students:weeks"


class TestCacheInvalidation:
    """Test cache invalidation functions."""

    def test_invalidate_term(self):
        """invalidate_term deletes schedule preview cache."""
        from cache import invalidate_term, cache, schedule_preview_key
        
        with patch.object(cache, 'delete') as mock_delete:
            invalidate_term(15)
            mock_delete.assert_called_once_with(schedule_preview_key(15))

    def test_invalidate_student_with_week(self):
        """invalidate_student with week deletes student summary."""
        from cache import invalidate_student, cache, student_summary_key
        
        with patch.object(cache, 'delete') as mock_delete:
            invalidate_student(7, "2025-09-08")
            mock_delete.assert_called_once_with(student_summary_key(7, "2025-09-08"))

    def test_invalidate_student_without_week(self):
        """invalidate_student without week does not delete (relies on TTL)."""
        from cache import invalidate_student, cache
        
        with patch.object(cache, 'delete') as mock_delete:
            invalidate_student(7)
            mock_delete.assert_not_called()


class TestGetOrSet:
    """Test the get_or_set convenience method."""

    def test_get_or_set_cache_hit(self):
        """get_or_set returns cached value without calling creator."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.get.return_value = "cached_value"
        
        cache = _BMemcachedCache(mock_client)
        creator_called = []
        
        def creator():
            creator_called.append(1)
            return "new_value"
        
        result = cache.get_or_set("key", creator)
        
        assert result == "cached_value"
        assert len(creator_called) == 0
        mock_client.set.assert_not_called()

    def test_get_or_set_cache_miss(self):
        """get_or_set calls creator and caches on miss."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_client.set.return_value = True
        
        cache = _BMemcachedCache(mock_client)
        
        def creator():
            return "computed_value"
        
        result = cache.get_or_set("key", creator, ttl_seconds=120)
        
        assert result == "computed_value"
        mock_client.set.assert_called_once_with("key", "computed_value", time=120)

    def test_get_or_set_does_not_cache_none(self):
        """get_or_set does not cache None values."""
        from cache import _BMemcachedCache
        
        mock_client = MagicMock()
        mock_client.get.return_value = None
        
        cache = _BMemcachedCache(mock_client)
        
        def creator():
            return None
        
        result = cache.get_or_set("key", creator)
        
        assert result is None
        mock_client.set.assert_not_called()
