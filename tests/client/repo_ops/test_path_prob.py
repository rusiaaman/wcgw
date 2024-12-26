import pytest
from wcgw.client.repo_ops.path_prob import FastPathAnalyzer
from unittest.mock import patch, mock_open, MagicMock


@pytest.fixture
def mock_tokenizer():
    tokenizer = MagicMock()
    encoding = MagicMock()
    encoding.tokens = ["test", "path", "token"]
    tokenizer.encode_batch.return_value = [encoding]
    tokenizer.decode.return_value = "test/path/token"
    return tokenizer


@pytest.fixture
def sample_vocab_content():
    return """test -1.5
path -2.0
token -1.8
unknown -3.0"""


def test_initialization(sample_vocab_content):
    with patch('builtins.open', mock_open(read_data=sample_vocab_content)):
        with patch('tokenizers.Tokenizer.from_file') as mock_tokenizer:
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            # Check if vocab was loaded correctly
            assert len(analyzer.vocab_probs) == 4
            assert analyzer.vocab_probs["test"] == -1.5
            assert analyzer.vocab_probs["path"] == -2.0
            assert analyzer.vocab_probs["token"] == -1.8
            assert analyzer.vocab_probs["unknown"] == -3.0


def test_tokenize_batch(mock_tokenizer):
    with patch('builtins.open', mock_open()):
        with patch('tokenizers.Tokenizer.from_file', return_value=mock_tokenizer):
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            # When we call tokenize_batch
            result = analyzer.tokenize_batch(["test/path"])
            assert result == [["test", "path", "token"]]
            mock_tokenizer.encode_batch.assert_called_once_with(["test/path"])


def test_detokenize(mock_tokenizer):
    with patch('builtins.open', mock_open()):
        with patch('tokenizers.Tokenizer.from_file', return_value=mock_tokenizer):
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            result = analyzer.detokenize(["test", "path", "token"])
            assert result == "test/path/token"
            mock_tokenizer.decode.assert_called_once()


def test_calculate_path_probability(sample_vocab_content, mock_tokenizer):
    mock_tokenizer.encode_batch.return_value = [MagicMock(tokens=["test", "path", "token"])]
    
    with patch('builtins.open', mock_open(read_data=sample_vocab_content)):
        with patch('tokenizers.Tokenizer.from_file', return_value=mock_tokenizer):
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            log_prob, tokens, unknown = analyzer.calculate_path_probability("test/path/token")
            
            # Expected probability: -1.5 + -2.0 + -1.8 = -5.3
            assert log_prob == -5.3
            assert tokens == ["test", "path", "token"]
            assert unknown == []


def test_calculate_path_probability_with_unknown_tokens(sample_vocab_content, mock_tokenizer):
    # Mock tokenizer to return some unknown tokens
    mock_tokenizer.encode_batch.return_value = [MagicMock(tokens=["test", "unknown_token", "path"])]
    
    with patch('builtins.open', mock_open(read_data=sample_vocab_content)):
        with patch('tokenizers.Tokenizer.from_file', return_value=mock_tokenizer):
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            log_prob, tokens, unknown = analyzer.calculate_path_probability("test/unknown/path")
            
            # Expected probability: -1.5 + -2.0 = -3.5 (unknown token probability not included)
            assert log_prob == -3.5
            assert tokens == ["test", "unknown_token", "path"]
            assert unknown == ["unknown_token"]


def test_invalid_vocab_line():
    invalid_vocab = """test -1.5
invalid_line
path -2.0"""
    
    with patch('builtins.open', mock_open(read_data=invalid_vocab)):
        with patch('tokenizers.Tokenizer.from_file') as mock_tokenizer:
            analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
            
            # Check if vocab was loaded correctly, skipping invalid line
            assert len(analyzer.vocab_probs) == 2
            assert analyzer.vocab_probs["test"] == -1.5
            assert analyzer.vocab_probs["path"] == -2.0


    def test_empty_path():
        with patch('builtins.open', mock_open(read_data="")):
            with patch('tokenizers.Tokenizer.from_file') as mock_tokenizer:
                mock_tokenizer_instance = Mock()
                mock_tokenizer_instance.encode.return_value.tokens = []
                mock_tokenizer.return_value = mock_tokenizer_instance
                
                analyzer = FastPathAnalyzer("model.bin", "vocab.txt")
                log_prob, tokens, unknown = analyzer.calculate_path_probability("")
                assert log_prob == 0.0
                assert tokens == []
            assert unknown == []