export function createSearchTokenizer(createMandarinTokenizer) {
  const tokenizer = createMandarinTokenizer();
  const tokenizeSegments = tokenizer.tokenize.bind(tokenizer);
  tokenizer.tokenize = (input, language, property, withCache) => {
    const tokens = tokenizeSegments(input, language, property, withCache);
    const normalized = tokens
      .map((token) => tokenizer.normalizeToken(property ?? "", String(token).toLowerCase(), withCache))
      .filter(Boolean);
    return tokenizer.allowDuplicates ? normalized : [...new Set(normalized)];
  };
  return tokenizer;
}
