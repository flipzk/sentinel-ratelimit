import pytest
from unittest.mock import AsyncMock
from sentinel.core.strategies.token_bucket import TokenBucketStrategy, RateLimitStatus

@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    # Default: allow request (1), 9 tokens remaining
    backend.eval_script.return_value = [1, 9.0]
    return backend

@pytest.mark.asyncio
async def test_allow_request(mock_backend):
    strategy = TokenBucketStrategy(mock_backend)
    
    result = await strategy.check("user:123", limit=10, window=60)
    
    assert result.status == RateLimitStatus.ALLOWED
    assert result.remaining == 9
    
    # Verify Lua script was called with correct keys
    call_args = mock_backend.eval_script.call_args
    assert call_args[1]['keys'][0] == "sentinel:tb:user:123"

@pytest.mark.asyncio
async def test_deny_request(mock_backend):
    strategy = TokenBucketStrategy(mock_backend)
    
    # Simulate Redis returning [0 (denied), 0.2 tokens left]
    mock_backend.eval_script.return_value = [0, 0.2]
    
    result = await strategy.check("user:123", limit=10, window=60)
    
    assert result.status == RateLimitStatus.DENIED
    assert result.retry_after > 0