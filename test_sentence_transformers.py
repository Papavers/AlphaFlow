"""
Local sentence-transformers embedding as fallback for RD-Agent.
No network dependency, runs locally using transformers + sentence-transformers.
"""
from sentence_transformers import SentenceTransformer

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using sentence-transformers locally."""
    # Use a small, fast model suitable for Chinese + English
    # Models: "all-MiniLM-L6-v2" (English), "paraphrase-multilingual-MiniLM-L12-v2" (multilingual)
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings.tolist()

def main():
    texts = ["你好，世界", "这是一个测试句子", "Hello world"]
    try:
        embeddings = get_embeddings(texts)
        print(f"成功获取 {len(embeddings)} 个 embeddings")
        print(f"每项向量长度: {len(embeddings[0])}")
        print(f"第一个向量前5个值: {embeddings[0][:5]}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"失败: {e}")

if __name__ == "__main__":
    main()
