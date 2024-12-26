from typing import Dict, List, Tuple

import tokenizers  # type: ignore[import-untyped]


class FastPathAnalyzer:
    def __init__(self, model_path: str, vocab_path: str) -> None:
        """Initialize with vocabulary."""
        # Load vocabulary and probabilities
        self.vocab_probs: Dict[str, float] = {}
        with open(vocab_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    token, prob = parts
                    try:
                        self.vocab_probs[token] = float(prob)
                    except ValueError:
                        continue

        self.encoder = tokenizers.Tokenizer.from_file(model_path)

    def tokenize_batch(self, texts: List[str]) -> List[List[str]]:
        """Tokenize multiple texts at once."""
        encodings = self.encoder.encode_batch(texts)
        return [encoding.tokens for encoding in encodings]

    def detokenize(self, tokens: List[str]) -> str:
        """Convert tokens back to text, handling special tokens."""
        return self.encoder.decode(tokens)  # type: ignore[no-any-return]

    def calculate_path_probabilities_batch(
        self, paths: List[str]
    ) -> List[Tuple[float, List[str], List[str]]]:
        """Calculate log probability for multiple paths at once."""
        # Batch tokenize all paths
        all_tokens = self.tokenize_batch(paths)

        results = []
        for tokens in all_tokens:
            # Calculate sum of log probabilities for each path
            log_prob_sum = 0.0
            unknown_tokens = []
            for token in tokens:
                if token in self.vocab_probs:
                    log_prob_sum += self.vocab_probs[token]
                else:
                    unknown_tokens.append(token)

            results.append((log_prob_sum, tokens, unknown_tokens))

        return results

    def calculate_path_probability(
        self, path: str
    ) -> Tuple[float, List[str], List[str]]:
        """Calculate log probability for a single path."""
        return self.calculate_path_probabilities_batch([path])[0]
